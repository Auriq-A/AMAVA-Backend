"""Teach Mode: the interactive recording wizard.

Opens a visible browser the user drives. The agent watches over their shoulder
via an in-page overlay (overlay.py), asking confirmation questions with buttons
and inputs. It learns the login form selectors, the products page, the target
count and the fields to extract, then saves all of it (disk + encrypted DB) so
the scraper never has to ask again.

    from supplier_scraper.teach import TeachWizard
    recipe = await TeachWizard("https://app.avasam.com").run()

Requires Playwright with a local Chromium (``playwright install chromium``).
The browser is always headed — the whole point is that the human does the
navigation and login, so there's no bot check to defeat.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from .overlay import OVERLAY_JS, buttons, info, text_input
from .recipe import RecipeStore, SupplierRecipe, domain_of, save_to_vault

_DEFAULT_FIELDS = "title, image, price, sku, asin/upc, brand, moq"


def _mask(value: str) -> str:
    if not value:
        return "(empty)"
    return "•" * min(len(value), 12) + f"  ({len(value)} chars)"


class TeachWizard:
    def __init__(
        self,
        start_url: str,
        *,
        recipe_store: RecipeStore | None = None,
        save_db: bool = True,
        user_email: str = "local@amava.dev",
    ) -> None:
        self.start_url = start_url
        self.domain = domain_of(start_url)
        self.store = recipe_store or RecipeStore()
        self.save_db = save_db
        self.user_email = user_email
        self._page = None
        self._answer_future: asyncio.Future | None = None

    # -- public ----------------------------------------------------------
    async def run(self) -> SupplierRecipe:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "playwright is not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            ) from exc

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False, args=["--start-maximized"])
            context = await browser.new_context(no_viewport=True)
            await context.add_init_script(OVERLAY_JS)
            await context.expose_binding("amavaAnswer", self._on_answer)
            page = await context.new_page()
            self._page = page
            await page.goto(self.start_url, wait_until="domcontentloaded")

            recipe, username, password = await self._collect()

            storage_state = await context.storage_state()
            await browser.close()

        # Persist: disk always; DB best-effort.
        recipe_path = self.store.save_recipe(recipe)
        session_path = self.store.save_session(self.domain, storage_state)
        self._saved = {"recipe_path": str(recipe_path), "session_path": str(session_path)}
        if self.save_db:
            user_id, err = save_to_vault(
                recipe, username=username, password=password, storage_state=storage_state,
                user_email=self.user_email,
            )
            self._saved["db_user_id"] = user_id
            self._saved["db_error"] = err
        return recipe

    @property
    def saved(self) -> dict[str, Any]:
        """Where things were written (populated after run())."""
        return getattr(self, "_saved", {})

    # -- the scripted conversation ---------------------------------------
    async def _collect(self) -> tuple[SupplierRecipe, str | None, str | None]:
        login_url = username_sel = password_sel = submit_sel = None
        username = password = None

        # 1) Login page (or skip if the site is public).
        ans = await self._ask(buttons(
            "Let's set up this supplier 👋",
            "Go to your LOGIN page in this browser window. When it's open in front "
            "of you, click below.\n\nIf this site has no login, choose the other option.",
            [("here", "I'm on the login page", "primary"),
             ("skip", "This site has no login", "ghost")],
        ))
        if ans["id"] == "here":
            login_url = await self._confirm_current_url(
                "Is this your login page?", allow_navigate=True
            )
            username_sel, username = await self._capture_field(
                "Your username / email",
                "Click your email/username box and TYPE it in. Then click below.",
                kind="username",
            )
            password_sel, password = await self._capture_field(
                "Your password",
                "Now click your password box and TYPE your password. Then click below.",
                kind="password",
            )
            submit_sel = await self._capture_login()

        # 2) Products page.
        ans = await self._ask(buttons(
            "Your products page 📦",
            "Browse to the page where you find your products most easily "
            "(your favourite catalog/search page).",
            [("nav", "I'll navigate there", "primary"),
             ("decide", "Decide for me", "ghost")],
        ))
        if ans["id"] == "decide":
            products_url = self._page.url
        else:
            products_url = await self._wait_then_confirm(
                "Navigate to your products page — I'll detect when you arrive.",
                "Scrape products from this page?",
            )

        # 2b) Learn what a product card looks like (so replay can wait for and
        # count them — many catalogs render products as non-link cards).
        product_selector = await self._capture_product()

        # 3) How many products (at least).
        ans = await self._ask(text_input(
            "How many products? 🔢",
            "At least how many products should I scrape each run?",
            placeholder="e.g. 50", value="50", input_type="number", submit_label="Set",
        ))
        try:
            min_products = max(1, int(float(ans.get("value") or 50)))
        except (TypeError, ValueError):
            min_products = 50

        # 4) Which fields to capture.
        ans = await self._ask(text_input(
            "Which fields? 🧾",
            "List the fields to capture for each product (comma or newline "
            "separated). Edit the defaults however you like.",
            value=_DEFAULT_FIELDS, multiline=True, submit_label="Save fields",
        ))
        fields = _parse_fields(ans.get("value") or _DEFAULT_FIELDS)

        # 5) Done.
        await self._show(info(
            "All set! 🎉",
            "Saved. I won't ask these questions again — next run I'll log in with "
            "your saved session and scrape straight away.\n\nSit back and relax. 🛋️",
        ))
        await asyncio.sleep(3)

        recipe = SupplierRecipe(
            domain=self.domain,
            start_url=self.start_url,
            products_url=products_url,
            login_url=login_url,
            username_selector=username_sel,
            password_selector=password_sel,
            submit_selector=submit_sel,
            product_selector=product_selector,
            min_products=min_products,
            fields=fields,
        )
        return recipe, username, password

    # -- step helpers ----------------------------------------------------
    async def _capture_field(self, title: str, prompt: str, *, kind: str):
        """Ask the user to type into a field, then confirm what we detected.

        ``kind`` is 'username' or 'password' (controls masking + the 3-way
        'actually it's the other one' option). Returns (selector, value).
        """
        other = "password" if kind == "username" else "username"
        while True:
            await self._eval("() => window.__amavaResetField && window.__amavaResetField()")
            await self._ask(buttons(title, prompt, [("ok", "I typed it ✓", "primary")]))
            fld = await self._eval("() => window.__amavaLastField && window.__amavaLastField()")
            if not fld or not fld.get("selector"):
                await self._ask(buttons(
                    "Hmm, I didn't catch a field",
                    "Click directly inside the box and type something, then try again.",
                    [("retry", "Try again", "primary")],
                ))
                continue
            shown = _mask(fld.get("value", "")) if kind == "password" else (fld.get("value") or "(empty)")
            ans = await self._ask(buttons(
                f"Confirm {kind}",
                f"Detected field:\n{fld['selector']}\nValue: {shown}\n\nIs this your {kind}?",
                [("yes", f"Yes, it's my {kind}", "primary"),
                 ("other", f"No — it's my {other}", "ghost"),
                 ("else", "No, something else", "danger")],
            ))
            if ans["id"] == "yes":
                return fld["selector"], fld.get("value", "")
            if ans["id"] == "else":
                continue  # re-capture this same kind
            # 'other': the user pointed at the OTHER field; record it as that and
            # loop to capture the originally-requested kind again.
            self._stash_other(other, fld["selector"], fld.get("value", ""))
            # fall through and re-ask for this kind

    def _stash_other(self, other_kind: str, selector: str, value: str) -> None:
        if not hasattr(self, "_stashed"):
            self._stashed = {}
        self._stashed[other_kind] = (selector, value)

    async def _capture_product(self) -> str | None:
        """Learn a CSS selector for a product card by having the user click one.

        Clicking a product usually navigates to its detail page, which resets
        the in-page overlay — so we DON'T wait on a button. We show an
        instruction and poll the captured click (mirrored to sessionStorage, so
        it survives the navigation). The overlay computes a 'repeating ancestor'
        selector that matches the whole product grid.
        """
        await self._eval("() => window.__amavaResetClick && window.__amavaResetClick()")
        await self._show(info(
            "Show me a product 🖱️",
            "Click ONE of your product cards or images so I learn what a product "
            "looks like.\n\nIt's fine if it opens the product page — I'll detect "
            "it automatically.",
        ))
        selector = await self._wait_for_card(timeout=90)
        if not selector:
            ans = await self._ask(buttons(
                "I didn't catch a product",
                "Click directly on a product card, then press below — or skip.",
                [("ok", "I clicked it ✓", "primary"), ("skip", "Skip — no cards", "ghost")],
            ))
            if ans["id"] == "skip":
                return None
            click = await self._eval("() => window.__amavaLastClick && window.__amavaLastClick()")
            selector = (click or {}).get("cardSelector")
        if selector:
            # We're on a stable page now (detail or listing), so a button works.
            await self._ask(buttons(
                "Got it 👍",
                f"I'll recognize products by:\n{selector}\n\nLooks right?",
                [("yes", "Yes", "primary"), ("ok", "Use it anyway", "ghost")],
            ))
        return selector

    async def _wait_for_card(self, *, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            click = await self._eval("() => window.__amavaLastClick && window.__amavaLastClick()")
            if click and click.get("cardSelector"):
                return click["cardSelector"]
            await asyncio.sleep(0.6)
        return None

    async def _capture_login(self) -> str | None:
        """Tell the user to log in; detect success by URL change; the button they
        clicked becomes the submit selector."""
        await self._eval("() => window.__amavaResetClick && window.__amavaResetClick()")
        await self._show(info(
            "Sign in now 🔐",
            "Click your site's Login button to sign in.\nI'll detect automatically "
            "when you're logged in — no need to click anything here.",
        ))
        prev = self._page.url
        changed = await self._wait_url_change(prev, timeout=300)
        click = await self._eval("() => window.__amavaLastClick && window.__amavaLastClick()")
        if not changed:
            # Login didn't navigate; ask the user to confirm they're in.
            await self._ask(buttons(
                "Are you logged in?",
                "I didn't detect a page change. If you're signed in, click below "
                "and I'll continue.",
                [("ok", "Yes, I'm logged in", "primary")],
            ))
        return (click or {}).get("selector")

    async def _confirm_current_url(self, question: str, *, allow_navigate: bool) -> str:
        url = self._page.url
        while True:
            opts = [("yes", "Yes", "primary")]
            if allow_navigate:
                opts.append(("no", "No, I'll navigate", "ghost"))
            ans = await self._ask(buttons("Confirm page", f"{question}\n{url}", opts))
            if ans["id"] == "yes":
                return url
            url = await self._wait_url_change(url, timeout=300) or self._page.url

    async def _wait_then_confirm(self, instruction: str, question: str) -> str:
        await self._show(info("Waiting… 🧭", instruction))
        prev = self._page.url
        await self._wait_url_change(prev, timeout=600)
        return await self._confirm_current_url(question, allow_navigate=True)

    # -- primitives ------------------------------------------------------
    def _on_answer(self, source: Any, payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            data = {"id": "?", "value": payload}
        fut = self._answer_future
        if fut is not None and not fut.done():
            fut.set_result(data)

    async def _ask(self, spec: dict[str, Any]) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        self._answer_future = loop.create_future()
        await self._render(spec)
        return await self._answer_future

    async def _show(self, spec: dict[str, Any]) -> None:
        await self._render(spec)

    async def _render(self, spec: dict[str, Any]) -> None:
        last_exc: Exception | None = None
        for _ in range(4):
            try:
                await self._page.evaluate("(s) => window.__amavaRender(s)", spec)
                return
            except Exception as exc:  # noqa: BLE001 - page mid-navigation; retry
                last_exc = exc
                try:
                    await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(0.4)
        if last_exc:
            raise last_exc

    async def _eval(self, expr: str) -> Any:
        try:
            return await self._page.evaluate(expr)
        except Exception:  # noqa: BLE001
            return None

    async def _wait_url_change(self, prev: str, *, timeout: float) -> str | None:
        """Poll page.url for a change (catches SPA route changes that don't fire
        navigation events). Returns the new URL, or None on timeout."""
        prev_norm = (prev or "").rstrip("/")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            cur = self._page.url
            if cur.rstrip("/") != prev_norm:
                await asyncio.sleep(0.8)  # let the new page settle
                return self._page.url
            await asyncio.sleep(0.4)
        return None


def _parse_fields(raw: str) -> list[str]:
    parts = [p.strip() for chunk in raw.split("\n") for p in chunk.split(",")]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            out.append(p)
    return out
