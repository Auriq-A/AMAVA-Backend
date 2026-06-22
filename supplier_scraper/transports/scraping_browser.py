"""Playwright-based browser transports.

_PlaywrightSessionBase — shared login/fetch/scroll/pagination logic.
ScrapingBrowserSession  — connects to Bright Data's remote browser over CDP.
LocalBrowserSession     — launches a local Chromium (see local_browser.py).
"""
from __future__ import annotations

import asyncio
import os

from ..config import ScraperConfig
from ..exceptions import LoginError, ScraperConfigError, TransportError
from ..models import LoginConfig
from .base import FetchResult, Transport


class _PlaywrightSessionBase(Transport):
    """Shared logic for all Playwright-backed sessions.

    Subclasses implement __aenter__ to set self._browser (either via
    connect_over_cdp for Bright Data or chromium.launch for local use).
    """

    name = "browser"

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    async def __aenter__(self) -> "_PlaywrightSessionBase":
        raise NotImplementedError  # pragma: no cover

    async def __aexit__(self, *exc: object) -> None:
        await self._cleanup()

    @property
    def url(self) -> str:
        """Current page URL (useful after click-based pagination)."""
        return self._page.url if self._page else ""

    async def _finish_context_setup(self) -> None:
        """Called by subclass __aenter__ once self._browser is connected/launched."""
        if self._browser.contexts:
            self._context = self._browser.contexts[0]
        else:
            self._context = await self._browser.new_context(**self._context_options())
        await self._apply_stealth()
        await self._install_resource_blocking()
        self._page = (
            self._context.pages[0] if self._context.pages
            else await self._context.new_page()
        )
        self._page.set_default_timeout(self._config.page_timeout_ms)

    def _context_options(self) -> dict:
        """Browser-context options applied when a new context is created.
        Overridden by the local session to look like a real browser."""
        return {}

    async def _apply_stealth(self) -> None:
        """Hook to mask automation signals. No-op by default (Bright Data
        handles this itself); overridden by the local session."""
        return None

    async def _install_resource_blocking(self) -> None:
        blocked = set(self._config.block_resources)
        if not blocked:
            return

        async def _route(route):
            if route.request.resource_type in blocked:
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", _route)

    async def dynamic_login(
        self,
        login_url: str,
        username: str,
        password: str,
        extractor,
    ) -> None:
        """Navigate to ``login_url``, ask Gemini to find the login form, fill
        and submit it. Works with any site — no hardcoded selectors needed.

        ``extractor`` must implement ``locate_login_form(html, page_url=...)``.
        Raises ``LoginError`` if the form can't be found or login doesn't succeed.
        """
        if self._logged_in:
            return
        page = self._page
        try:
            await page.goto(login_url, wait_until=self._config.nav_wait_until)
            # SPA login pages render the form via JS after the initial HTML.
            # Wait for a password field to appear before reading the DOM, else
            # Gemini sees an empty shell. Fall back to network-idle if there's
            # no <input type=password> (e.g. multi-step or custom widgets).
            try:
                await page.wait_for_selector("input[type='password']", timeout=15_000)
            except Exception:  # noqa: BLE001 - not all login pages have one yet
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:  # noqa: BLE001
                    pass
            html = await page.content()
        except Exception as exc:  # noqa: BLE001
            raise LoginError(f"Could not load login page {login_url}: {exc}") from exc

        locators = await extractor.locate_login_form(html, page_url=login_url)

        missing = [k for k in ("username_selector", "password_selector", "submit_selector")
                   if not locators.get(k)]
        if missing:
            # Diagnostics: did the page even render a form?
            n_inputs = await page.locator("input").count()
            n_pw = await page.locator("input[type='password']").count()
            final_url = page.url
            try:
                title = await page.title()
            except Exception:  # noqa: BLE001
                title = "?"
            debug_path = self._dump_debug_html(login_url, html)
            raise LoginError(
                f"Gemini could not find login form fields on {login_url}: "
                f"missing {missing}.\n"
                f"  final URL : {final_url}\n"
                f"  page title: {title!r}\n"
                f"  rendered  : {n_inputs} <input>, {n_pw} password field(s)\n"
                f"  saved HTML: {debug_path}\n"
                + (
                    "  -> No password field rendered. The page is likely behind a "
                    "bot check, the login URL redirected, or the form loads later. "
                    "Set LOCAL_BROWSER_HEADLESS=false to watch the browser, open "
                    "the saved HTML to see what came back."
                    if n_pw == 0 else
                    "  -> A password field exists but Gemini didn't return "
                    "selectors. Add a LoginConfig with manual selectors."
                )
            )

        login_page_url = page.url
        try:
            await page.fill(locators["username_selector"], username)
            await page.fill(locators["password_selector"], password)
            await page.click(locators["submit_selector"])
            # Wait for navigation away from the login page (success signal).
            await page.wait_for_url(
                lambda url: url != login_page_url,
                timeout=15_000,
            )
        except Exception as exc:  # noqa: BLE001
            raise LoginError(
                f"Login form submission failed on {login_url}: {exc}"
            ) from exc

        self._logged_in = True

    @staticmethod
    def _dump_debug_html(source_url: str, html: str) -> str:
        """Write captured HTML to a temp file for debugging; return its path."""
        import tempfile, os
        try:
            fd, path = tempfile.mkstemp(prefix="login_debug_", suffix=".html")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"<!-- captured from {source_url} -->\n")
                fh.write(html)
            return path
        except Exception:  # noqa: BLE001 - debugging aid, never fatal
            return "(could not write debug HTML)"

    async def login(
        self, login: LoginConfig, *, username: str | None = None, password: str | None = None
    ) -> None:
        """Perform the declarative login flow once per session.

        Explicit ``username``/``password`` (e.g. a per-user secret from the
        vault) take priority; otherwise fall back to the env vars named in the
        LoginConfig."""
        if self._logged_in:
            return
        username = username or os.getenv(login.username_env)
        password = password or os.getenv(login.password_env)
        if not username or not password:
            raise ScraperConfigError(
                f"Missing login credentials: provide them explicitly or set "
                f"{login.username_env} and {login.password_env} in the environment."
            )
        page = self._page
        try:
            await page.goto(login.url, wait_until=self._config.nav_wait_until)
            await page.fill(login.username_selector, username)
            await page.fill(login.password_selector, password)
            await page.click(login.submit_selector)
            if login.success_selector:
                await page.wait_for_selector(login.success_selector)
            else:
                await page.wait_for_timeout(login.wait_after_ms)
        except Exception as exc:  # noqa: BLE001
            raise LoginError(f"Login to {login.url} failed: {exc}") from exc
        self._logged_in = True

    async def fetch(
        self, url: str, *, wait_for: str | None = None, scroll_count: int = 0
    ) -> FetchResult:
        page = self._page
        try:
            await page.goto(url, wait_until=self._config.nav_wait_until)
            if wait_for:
                await page.wait_for_selector(wait_for)
            if scroll_count > 0:
                # Scroll to trigger lazy-load / infinite-scroll content.
                for _ in range(scroll_count):
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(600)
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(500)
            html = await page.content()
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"Failed to load {url}: {exc}", url=url) from exc
        return FetchResult(url=url, html=html, status_code=200)

    async def click_next(self, next_selector: str, *, wait_for: str | None = None) -> str | None:
        """Click a 'next page' element and return the new HTML, or None if the
        element isn't present (end of pagination)."""
        page = self._page
        el = await page.query_selector(next_selector)
        if el is None:
            return None
        try:
            await el.click()
            await page.wait_for_load_state(self._config.nav_wait_until)
            if wait_for:
                await page.wait_for_selector(wait_for)
            else:
                await page.wait_for_timeout(800)
            return await page.content()
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"Pagination click failed: {exc}") from exc

    async def _cleanup(self) -> None:
        for closer in (
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            if closer:
                try:
                    result = closer()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:  # noqa: BLE001 - best-effort teardown
                    pass
        self._browser = None
        self._pw = None


class ScrapingBrowserSession(_PlaywrightSessionBase):
    """Connects Playwright to Bright Data's remote browser over CDP.

    Cost note: billed per GB — by default we abort image/media/font/stylesheet
    requests (config.block_resources). That typically cuts bandwidth 5-10x.
    """

    name = "browser"

    def __init__(self, config: ScraperConfig) -> None:
        config.bright_data.require_browser()  # fail fast if credentials missing
        super().__init__(config)

    async def __aenter__(self) -> "ScrapingBrowserSession":
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ScraperConfigError(
                "playwright is not installed. Run: pip install playwright  "
                "(no 'playwright install' needed - we connect to a remote browser)."
            ) from exc

        self._pw = await async_playwright().start()
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                self._config.bright_data.browser_cdp_url,
                timeout=self._config.page_timeout_ms,
            )
        except Exception as exc:  # noqa: BLE001
            await self._cleanup()
            raise TransportError(f"Could not connect to Scraping Browser: {exc}") from exc

        await self._finish_context_setup()
        return self
