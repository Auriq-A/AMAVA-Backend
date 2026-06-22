"""Replay a learned recipe — the hands-off scrape.

Loads a ``SupplierRecipe`` + the saved session cookies, opens a browser already
authenticated (no login prompt), navigates to the products page, scrolls to
pull in lazy-loaded items, and runs the Gemini extractor with the fields the
user chose during teaching. If the saved session has expired it re-logs-in
automatically using the recipe's selectors + the credentials in the vault.

    from supplier_scraper.teach import replay
    result = await replay("https://app.avasam.com")
    for p in result.products:
        print(p.title, p.price, p.product_url)

Headed by default: gated SPAs (avasam) refuse to render under headless even with
a valid session, so we drive a visible-but-automated browser. Pass
``headless=True`` to try headless for sites that allow it.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from ..extraction import GeminiExtractor
from ..extraction.html_clean import extract_product_links
from ..models import Product, ScrapeResult
from .recipe import RecipeStore, SupplierRecipe, domain_of, load_from_vault

# Stealth flags so the automated browser isn't flagged outright (same intent as
# the local transport's). Doesn't fully beat fingerprinting — that's why we
# default to headed.
_LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def replay(
    target: str,
    *,
    recipe_store: RecipeStore | None = None,
    headless: bool = False,
    max_products: int | None = None,
    user_email: str = "local@amava.dev",
    extractor: GeminiExtractor | None = None,
    load_timeout: float = 90.0,
) -> ScrapeResult:
    """Run a saved recipe and return the scraped products.

    ``target`` may be a domain ("app.avasam.com") or any URL on the site.
    ``max_products`` overrides the recipe's ``min_products`` target.
    ``load_timeout`` is how long (seconds) to wait for a slow site's products
    to render before giving up (avasam is slow — keep this generous).
    """
    domain = domain_of(target) if "://" in target else target.lower()
    store = recipe_store or RecipeStore()

    # Prefer the disk recipe; fall back to the DB vault. Credentials only ever
    # come from the vault (never written to the disk recipe).
    recipe = store.load_recipe(domain)
    creds: dict[str, str] | None
    vault_recipe, creds, vault_session = load_from_vault(domain, user_email=user_email)
    if recipe is None:
        recipe = vault_recipe
    if recipe is None:
        raise FileNotFoundError(
            f"No recipe for {domain!r}. Teach it first: "
            f"python -m supplier_scraper.teach https://{domain}"
        )

    storage_state = store.load_session(domain) or vault_session
    target_n = max_products or recipe.min_products
    result = ScrapeResult(source=domain, transport_used="teach_replay")

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright "
            "&& playwright install chromium"
        ) from exc

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        context = await browser.new_context(
            storage_state=storage_state or None,
            user_agent=_USER_AGENT,
            no_viewport=not headless,
            viewport={"width": 1366, "height": 900} if headless else None,
            locale="en-US",
        )
        page = await context.new_page()
        try:
            await page.goto(recipe.products_url, wait_until="domcontentloaded")
            await _settle(page)

            relogged = False
            if await _needs_login(page, recipe):
                if recipe.requires_login and creds and creds.get("password"):
                    await _relogin(page, recipe, creds, result)
                    await page.goto(recipe.products_url, wait_until="domcontentloaded")
                    await _settle(page)
                    relogged = True
                else:
                    result.errors.append(
                        "Saved session expired and no stored credentials to "
                        "re-login. Re-run Teach Mode to refresh the session."
                    )

            link_count = await _load_products(
                page, target_n, product_selector=recipe.product_selector, timeout=load_timeout
            )
            html = await page.content()
            final_url = page.url
            # Focused extraction: pull just the product cards' HTML (matched by
            # the learned selector). Far smaller + guaranteed to contain the
            # products and their links — instead of the whole boilerplate page.
            cards_html = await _collect_cards_html(
                page, recipe.product_selector, max(target_n * 2, 60)
            )

            # Refresh cookies if we re-logged-in, so next replay stays logged in.
            try:
                store.save_session(domain, await context.storage_state())
            except Exception:  # noqa: BLE001
                pass
        finally:
            await browser.close()

    # Diagnostics — so a 0-product run is debuggable instead of silent.
    debug_path = _dump_html(store, domain, recipe.products_url, final_url, html)
    result.metadata.update({
        "final_url": final_url,
        "products_detected": link_count,
        "product_selector": recipe.product_selector,
        "html_chars": len(html),
        "relogged_in": relogged,
        "debug_html": debug_path,
    })

    ext = extractor or GeminiExtractor()
    extract_html = cards_html or html
    try:
        products = await ext.extract(
            extract_html, page_url=recipe.products_url, hint=_fields_hint(recipe.fields)
        )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"extraction failed: {exc}")
        products = []

    result.products.extend(products)
    result.pages_scraped = 1
    result.metadata["target_products"] = target_n
    result.metadata["fields"] = recipe.fields
    result.metadata["extracted_from"] = "product cards" if cards_html else "full page"
    result.metadata["cards_html_chars"] = len(cards_html or "")
    return result


# --- helpers ---------------------------------------------------------------
async def _settle(page) -> None:
    """Brief settle after navigation. We don't rely on networkidle — analytics/
    chat scripts on sites like avasam keep the network busy so it never fires;
    _load_products does the real patient waiting for products to appear."""
    try:
        await page.wait_for_load_state("networkidle", timeout=6_000)
    except Exception:  # noqa: BLE001
        pass
    await page.wait_for_timeout(1000)


def _dump_html(store: RecipeStore, domain: str, products_url: str, final_url: str, html: str) -> str:
    """Write the captured products-page HTML to instance/debug for inspection."""
    from pathlib import Path
    import re as _re
    try:
        debug_dir = Path(store.base) / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        slug = _re.sub(r"[^a-z0-9.-]+", "_", domain.lower()).strip("_") or "site"
        path = debug_dir / f"replay_{slug}_{int(time.time())}.html"
        path.write_text(
            f"<!-- products_url: {products_url} -->\n"
            f"<!-- final_url:    {final_url} -->\n" + html,
            encoding="utf-8",
        )
        return str(path)
    except Exception:  # noqa: BLE001
        return "(could not write debug HTML)"


async def _needs_login(page, recipe: SupplierRecipe) -> bool:
    """True if we appear to have landed on a login page instead of products."""
    if not recipe.requires_login:
        return False
    url = page.url.lower()
    if "login" in url or "signin" in url or "sign-in" in url:
        return True
    # Or the password field from the recipe is present on this page.
    if recipe.password_selector:
        try:
            return await page.locator(recipe.password_selector).count() > 0
        except Exception:  # noqa: BLE001
            return False
    return False


async def _relogin(page, recipe: SupplierRecipe, creds: dict[str, str], result: ScrapeResult) -> None:
    try:
        if page.url.rstrip("/") != (recipe.login_url or "").rstrip("/") and recipe.login_url:
            await page.goto(recipe.login_url, wait_until="domcontentloaded")
        await page.wait_for_selector(recipe.password_selector, timeout=15_000)
        await page.fill(recipe.username_selector, creds.get("username", ""))
        await page.fill(recipe.password_selector, creds.get("password", ""))
        if recipe.submit_selector:
            await page.click(recipe.submit_selector)
        else:
            await page.press(recipe.password_selector, "Enter")
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"re-login failed: {exc}")


async def _collect_cards_html(page, product_selector: str | None, limit: int) -> str | None:
    """Return the concatenated outerHTML of up to ``limit`` product cards matched
    by the learned selector — a small, product-only payload for the extractor.
    None if there's no selector or nothing matched."""
    if not product_selector:
        return None
    try:
        html = await page.evaluate(
            """([sel, lim]) => {
                const els = Array.from(document.querySelectorAll(sel)).slice(0, lim);
                return els.map(e => e.outerHTML).join('\\n');
            }""",
            [product_selector, limit],
        )
        return html or None
    except Exception:  # noqa: BLE001
        return None


async def _count_products(page, product_selector: str | None) -> int:
    """Count products currently in the DOM: by the learned card selector if we
    have one, else by product-looking links."""
    if product_selector:
        try:
            return await page.locator(product_selector).count()
        except Exception:  # noqa: BLE001
            return 0
    try:
        html = await page.content()
    except Exception:  # noqa: BLE001
        return 0
    return len(extract_product_links(html, page.url))


async def _load_products(
    page, target_n: int, *, product_selector: str | None = None,
    timeout: float = 90.0, poll: float = 1.5,
) -> int:
    """Wait (patiently) for a slow SPA's products to render, then scroll to pull
    in more, until we reach ``target_n`` or the list stops growing or we hit
    ``timeout`` seconds. Returns the product count seen.

    Crucially: while zero products are visible we keep waiting (the page is
    still loading) instead of bailing — that's the avasam slow-load case. We
    only treat "stagnant" as done once products have actually appeared.
    """
    deadline = time.monotonic() + timeout
    prev = -1
    stagnant = 0
    seen_any = False
    poll_ms = int(poll * 1000)
    while time.monotonic() < deadline:
        count = await _count_products(page, product_selector)
        if count >= target_n:
            return count
        if count > 0:
            seen_any = True
        if count == prev:
            stagnant += 1
            # Only give up once products have shown AND stopped growing.
            if seen_any and stagnant >= 4:
                return count
        else:
            stagnant = 0
        prev = count
        # Scroll to the bottom — avasam-style infinite lists lazy-load when you
        # reach the end of the page, not just on a partial scroll.
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(poll_ms)
    return max(prev, 0)


def _fields_hint(fields: list[str]) -> str:
    if not fields:
        return ""
    return (
        "The user is most interested in these fields for each product: "
        + ", ".join(fields)
        + ". Populate them wherever present (map 'asin/upc' to upc/ean, anything "
        "without a dedicated column into 'extra')."
    )


# --- CLI -------------------------------------------------------------------
def main() -> int:
    import sys

    argv = sys.argv[1:]
    headless = "--headless" in argv
    load_timeout = 90.0
    rest = []
    it = iter(argv)
    for a in it:
        if a == "--headless":
            continue
        if a == "--timeout":
            load_timeout = float(next(it, 90))
            continue
        rest.append(a)
    if len(rest) != 1 or rest[0] in ("-h", "--help"):
        print("Usage: python -m supplier_scraper.teach.replay <domain-or-url> "
              "[--headless] [--timeout SECONDS]")
        return 1

    async def _run() -> int:
        result = await replay(rest[0], headless=headless, load_timeout=load_timeout)
        m = result.metadata
        print(f"\nScraped {result.count} products from {result.source}")
        for p in result.products[:10]:
            print(f"  - {p.title}  |  {p.price} {p.currency or ''}  |  {p.product_url or ''}")
        print("\nDiagnostics:")
        print(f"  final URL          : {m.get('final_url')}")
        print(f"  products detected  : {m.get('products_detected')}")
        print(f"  product selector   : {m.get('product_selector')}")
        print(f"  extracted from     : {m.get('extracted_from')} "
              f"({m.get('cards_html_chars')} chars)")
        print(f"  full HTML captured : {m.get('html_chars')} chars")
        print(f"  re-logged in       : {m.get('relogged_in')}")
        print(f"  saved page HTML    : {m.get('debug_html')}")
        if result.errors:
            print("\nErrors:")
            for e in result.errors:
                print(f"  ! {e}")
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
