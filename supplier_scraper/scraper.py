"""SupplierScraper - the orchestrator / facade.

Routes each scrape to the right transport (browser for gated sites, Web Unlocker
for public ones), walks pagination, and runs Gemini extraction on each page.
Async-first to fit the ADK agent; sync convenience wrappers provided.

    from supplier_scraper import SupplierScraper

    scraper = SupplierScraper()                       # reads env
    result = await scraper.scrape("https://supplier.com/catalog", max_pages=3)
    result = await scraper.scrape_supplier("avasam", max_pages=5)
    for p in result.products:
        print(p.title, p.price)

Dynamic login (no hardcoded selectors):
    result = await scraper.scrape(
        "https://app.avasam.com/seller/products",
        login_url="https://app.avasam.com/login",
        username="your@email.com",
        password="yourpassword",
        scroll_count=15,
        enrich=True,
    )

Set BRIGHTDATA_USE=false to skip Bright Data and use plain httpx / local
Playwright instead (useful for development and unblocked public sites).
"""
from __future__ import annotations

import asyncio
import math
from typing import Callable
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from .config import ScraperConfig
from .exceptions import ScraperConfigError
from .extraction import Extractor, GeminiExtractor
from .models import PaginationConfig, Product, ScrapeResult, SupplierProfile
from .suppliers import get_supplier
from .transports import (
    LocalBrowserSession,
    LocalHttpTransport,
    ScrapingBrowserSession,
    WebUnlockerTransport,
)


class SupplierScraper:
    def __init__(
        self,
        config: ScraperConfig | None = None,
        *,
        extractor: Extractor | None = None,
        credential_provider: Callable[[str], tuple[str, str] | None] | None = None,
    ) -> None:
        self.config = config or ScraperConfig.from_env()
        # Extractor is created lazily so constructing the scraper needs no API
        # key and performs no network. Inject one to override (e.g. in tests).
        self._extractor = extractor
        # Optional per-supplier login resolver: name -> (username, password).
        # The multi-tenant layer injects this to supply each user's own creds;
        # when None, login falls back to the env vars in the LoginConfig.
        self._credential_provider = credential_provider

    # -- public API -------------------------------------------------------
    async def scrape(
        self,
        url: str,
        *,
        max_pages: int | None = None,
        transport: str = "auto",
        requires_login: bool = False,
        wait_for: str | None = None,
        hint: str = "",
        pagination: PaginationConfig | None = None,
        enrich: bool = False,
        max_enrich: int | None = None,
        scroll_count: int = 0,
        login_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> ScrapeResult:
        """Scrape any URL. Supports dynamic login via Gemini — no hardcoded
        selectors needed.

        ``login_url`` / ``username`` / ``password`` — when provided, the
        scraper navigates to ``login_url`` first, asks Gemini to locate the
        login form, fills it in with the given credentials, and proceeds to
        scrape ``url`` in the same (now-authenticated) session. Requires the
        browser transport (set automatically when these params are given).

        ``scroll_count`` — window-height scrolls before reading each catalog
        page (browser transport only). Use ~15 for infinite-scroll sites.

        If ``enrich`` is True, also visit each product's detail page and
        merge in fuller info (description, images, specifications, rating,
        stock). Capped by ``max_enrich`` (pass ``0`` for no cap).
        """
        if login_url and transport == "auto":
            transport = "browser"
            requires_login = True
        profile = SupplierProfile(
            name=url,
            base_url=url,
            requires_login=requires_login,
            transport=transport,
            pagination=pagination or PaginationConfig(),
            extraction_hint=hint,
            wait_for=wait_for,
            scroll_count=scroll_count,
        )
        return await self._run(
            profile, start_url=url, max_pages=max_pages,
            enrich=enrich, max_enrich=max_enrich,
            login_url=login_url, username=username, password=password,
        )

    async def scrape_supplier(
        self,
        supplier: str | SupplierProfile,
        *,
        start_url: str | None = None,
        max_pages: int | None = None,
        enrich: bool = False,
        max_enrich: int | None = None,
    ) -> ScrapeResult:
        """Scrape a registered supplier by name (or a SupplierProfile).

        See ``scrape()`` for the ``enrich`` / ``max_enrich`` behaviour.
        """
        profile = supplier if isinstance(supplier, SupplierProfile) else get_supplier(supplier)
        return await self._run(
            profile, start_url=start_url or profile.base_url, max_pages=max_pages,
            enrich=enrich, max_enrich=max_enrich,
        )

    # Sync convenience wrappers for non-async callers / CLIs.
    def scrape_sync(self, *args, **kwargs) -> ScrapeResult:
        return asyncio.run(self.scrape(*args, **kwargs))

    def scrape_supplier_sync(self, *args, **kwargs) -> ScrapeResult:
        return asyncio.run(self.scrape_supplier(*args, **kwargs))

    # -- core flow --------------------------------------------------------
    async def _run(
        self,
        profile: SupplierProfile,
        *,
        start_url: str,
        max_pages: int | None,
        enrich: bool = False,
        max_enrich: int | None = None,
        login_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> ScrapeResult:
        max_pages = self._resolve_max_pages(profile, max_pages)
        kind = profile.resolve_transport()
        result = ScrapeResult(source=profile.name, transport_used=kind)
        extractor = self._get_extractor()
        cap = self._resolve_enrich_cap(enrich, max_enrich)

        if kind == "unlocker":
            await self._collect_unlocker(profile, start_url, max_pages, result, extractor, cap)
        else:
            await self._collect_browser(
                profile, start_url, max_pages, result, extractor, cap,
                login_url=login_url, username=username, password=password,
            )

        return result

    async def _collect_unlocker(self, profile, start_url, max_pages, result, extractor, cap):
        if profile.pagination.strategy == "next_button":
            result.errors.append(
                "next_button pagination needs the browser transport; "
                "scraping first page only via Web Unlocker."
            )
        all_products: list[Product] = []
        TransportCls = (
            WebUnlockerTransport if self.config.bright_data.use_bright_data
            else LocalHttpTransport
        )
        async with TransportCls(self.config.bright_data) as transport:
            for page_url in self._page_urls(start_url, profile.pagination, max_pages):
                fr = await transport.fetch(page_url, wait_for=profile.wait_for)
                result.pages_scraped += 1
                all_products.extend(
                    await self._extract_one(extractor, fr.html, page_url, profile, result)
                )
                await asyncio.sleep(self.config.page_delay)

            if cap:
                await self._enrich_products(
                    transport.fetch, extractor, all_products, profile, result, cap
                )

        result.products.extend(all_products)

    async def _collect_browser(
        self, profile, start_url, max_pages, result, extractor, cap,
        *, login_url=None, username=None, password=None,
    ):
        all_products: list[Product] = []
        SessionCls = (
            ScrapingBrowserSession if self.config.bright_data.use_bright_data
            else LocalBrowserSession
        )
        async with SessionCls(self.config) as session:
            if login_url and username and password:
                # Dynamic login: Gemini finds the form selectors automatically.
                await session.dynamic_login(login_url, username, password, extractor)
            elif profile.requires_login:
                if not profile.login:
                    raise ScraperConfigError(
                        f"Supplier {profile.name!r} requires login but has no "
                        "LoginConfig."
                    )
                creds = (
                    self._credential_provider(profile.name)
                    if self._credential_provider
                    else None
                )
                _username, _password = creds if creds else (None, None)
                await session.login(profile.login, username=_username, password=_password)

            if profile.pagination.strategy == "next_button" and profile.pagination.next_selector:
                fr = await session.fetch(
                    start_url, wait_for=profile.wait_for, scroll_count=profile.scroll_count
                )
                result.pages_scraped += 1
                all_products.extend(
                    await self._extract_one(extractor, fr.html, fr.url, profile, result)
                )
                for _ in range(max_pages - 1):
                    html = await session.click_next(
                        profile.pagination.next_selector, wait_for=profile.wait_for
                    )
                    if html is None:
                        break
                    result.pages_scraped += 1
                    all_products.extend(
                        await self._extract_one(extractor, html, session.url, profile, result)
                    )
                    await asyncio.sleep(self.config.page_delay)
            else:
                for page_url in self._page_urls(start_url, profile.pagination, max_pages):
                    fr = await session.fetch(
                        page_url, wait_for=profile.wait_for, scroll_count=profile.scroll_count
                    )
                    result.pages_scraped += 1
                    all_products.extend(
                        await self._extract_one(extractor, fr.html, page_url, profile, result)
                    )
                    await asyncio.sleep(self.config.page_delay)

            # Enrichment runs last (after pagination is done) so navigating to
            # detail pages can't disturb a "click next" flow, and it reuses
            # this same (already-logged-in) session.
            if cap:
                await self._enrich_products(
                    session.fetch, extractor, all_products, profile, result, cap
                )

        result.products.extend(all_products)

    async def _extract_one(self, extractor, html, page_url, profile, result) -> list[Product]:
        try:
            return await extractor.extract(
                html, page_url=page_url, hint=profile.extraction_hint
            )
        except Exception as exc:  # noqa: BLE001 - record, keep going
            result.errors.append(f"extraction failed for {page_url}: {exc}")
            return []

    async def _enrich_products(self, fetch, extractor, products, profile, result, cap):
        """Visit each product's detail page (up to ``cap``) and merge fuller
        info into it via ``extractor.extract_detail``.

        ``fetch`` is the already-open transport's/session's fetch coroutine,
        reused so a logged-in session stays logged in for detail pages.
        """
        enriched = 0
        for product in products:
            if enriched >= cap:
                break
            url = product.product_url
            if not url:
                continue
            try:
                fr = await fetch(url, wait_for=profile.detail_wait_for)
                detail = await extractor.extract_detail(
                    fr.html, page_url=url, hint=profile.extraction_hint
                )
                if detail is not None:
                    product.merge_detail(detail)
                enriched += 1
            except Exception as exc:  # noqa: BLE001 - record, keep going
                result.errors.append(f"enrichment failed for {url}: {exc}")
            await asyncio.sleep(self.config.page_delay)
        result.metadata["products_enriched"] = enriched

    # -- helpers ----------------------------------------------------------
    def _get_extractor(self) -> Extractor:
        if self._extractor is None:
            self._extractor = GeminiExtractor(
                model=self.config.extraction_model,
                max_html_chars=self.config.max_html_chars,
            )
        return self._extractor

    def _resolve_max_pages(self, profile: SupplierProfile, override: int | None) -> int:
        if override is not None:
            return max(1, override)
        if profile.pagination and profile.pagination.max_pages:
            return max(1, profile.pagination.max_pages)
        return max(1, self.config.default_max_pages)

    def _resolve_enrich_cap(self, enrich: bool, override: int | None) -> int | float:
        """Return how many products to enrich: 0 disables it, math.inf means
        no cap (enrich every product with a product_url)."""
        if not enrich:
            return 0
        if override is None:
            return max(0, self.config.default_max_enrich)
        if override <= 0:
            return math.inf
        return override

    @staticmethod
    def _page_urls(start_url: str, pagination: PaginationConfig, max_pages: int):
        # Only "query" pagination can derive page URLs up front; everything else
        # is a single page here (next_button is handled in the browser path).
        if pagination.strategy != "query" or max_pages <= 1:
            yield start_url
            return
        parsed = urlparse(start_url)
        base_q = dict(parse_qsl(parsed.query))
        start = pagination.start_page
        for i in range(start, start + max_pages):
            q = {**base_q, pagination.page_param: i}
            yield urlunparse(parsed._replace(query=urlencode(q)))


if "__main__" == __name__:
    async def main():
        scraper = SupplierScraper()

        result = await scraper.scrape(
            "https://app.avasam.com/seller/products",
            login_url="https://app.avasam.com/login",
            username="info@sayaholdingllc.com",
            password="AmazonFBA$1483",
            scroll_count=15,
            enrich=True,
        )
        print(f"Found {result.count} products")
        for p in result.products[:3]:
            print(p.title, p.price, p.product_url)
        return result

    asyncio.run(main())
