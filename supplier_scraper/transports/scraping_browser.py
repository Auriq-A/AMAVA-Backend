"""Scraping Browser transport (stateful, for gated/interactive sites).

Connects Playwright to Bright Data's remote browser over CDP - no local browser
binary is downloaded. Bright Data handles proxies/unblocking/CAPTCHA; we drive
navigation, login and pagination.

Cost note: this product is billed per GB, so by default we abort image/media/
font/stylesheet requests (config.block_resources). That typically cuts page
bandwidth 5-10x. Disable per-supplier if a site breaks without its assets.
"""
from __future__ import annotations

import asyncio
import os

from ..config import ScraperConfig
from ..exceptions import LoginError, ScraperConfigError, TransportError
from ..models import LoginConfig
from .base import FetchResult, Transport


class ScrapingBrowserSession(Transport):
    """An open browser session. Use as an async context manager so the remote
    browser is always closed (and billing stops)."""

    name = "browser"

    def __init__(self, config: ScraperConfig) -> None:
        config.bright_data.require_browser()
        self._config = config
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

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

        self._context = self._browser.contexts[0] if self._browser.contexts \
            else await self._browser.new_context()
        await self._install_resource_blocking()
        self._page = self._context.pages[0] if self._context.pages \
            else await self._context.new_page()
        self._page.set_default_timeout(self._config.page_timeout_ms)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._cleanup()

    @property
    def url(self) -> str:
        """Current page URL (useful after click-based pagination)."""
        return self._page.url if self._page else ""

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

    async def fetch(self, url: str, *, wait_for: str | None = None) -> FetchResult:
        page = self._page
        try:
            await page.goto(url, wait_until=self._config.nav_wait_until)
            if wait_for:
                await page.wait_for_selector(wait_for)
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
