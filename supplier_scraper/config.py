"""Bright Data + extraction configuration, hydrated from the environment.

Two dataclasses:
  * BrightDataConfig - credentials/endpoints for the two transports.
  * ScraperConfig    - everything the SupplierScraper needs at runtime
                       (Bright Data config, Gemini model, cost/perf tunables).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .exceptions import ScraperConfigError

try:  # optional .env loading (project already uses dotenv via ADK)
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass


# Resource types worth blocking in the browser transport. Bright Data Scraping
# Browser bills per GB, so dropping images/media/fonts/css is the single biggest
# cost lever (typically 5-10x less bandwidth per page).
DEFAULT_BLOCKED_RESOURCES = ("image", "media", "font", "stylesheet")


@dataclass
class BrightDataConfig:
    """Bright Data credentials for both transports.

    Scraping Browser (gated/interactive sites):
        browser_auth = "brd-customer-<id>-zone-<zone>:<password>"
    Web Unlocker (public/static pages):
        api_token + unlocker_zone
    """

    # Set BRIGHTDATA_USE=false to skip Bright Data and use plain httpx (unlocker
    # path) or local Playwright (browser path) instead. Useful for development
    # and for public sites that don't block plain HTTP requests.
    use_bright_data: bool = True
    # Scraping Browser
    browser_auth: str | None = None
    browser_host: str = "brd.superproxy.io"
    browser_port: int = 9222
    # Web Unlocker
    api_token: str | None = None
    unlocker_zone: str | None = None
    unlocker_endpoint: str = "https://api.brightdata.com/request"

    @classmethod
    def from_env(cls, prefix: str = "BRIGHTDATA_") -> "BrightDataConfig":
        use_val = os.getenv("BRIGHTDATA_USE", "true").strip().lower()
        return cls(
            use_bright_data=use_val not in ("false", "0", "no", "off"),
            browser_auth=os.getenv(f"{prefix}BROWSER_AUTH"),
            browser_host=os.getenv(f"{prefix}BROWSER_HOST", "brd.superproxy.io"),
            browser_port=int(os.getenv(f"{prefix}BROWSER_PORT", "9222")),
            api_token=os.getenv(f"{prefix}API_TOKEN"),
            unlocker_zone=os.getenv(f"{prefix}UNLOCKER_ZONE"),
            unlocker_endpoint=os.getenv(
                f"{prefix}UNLOCKER_ENDPOINT", "https://api.brightdata.com/request"
            ),
        )

    @property
    def browser_cdp_url(self) -> str:
        """The wss:// endpoint Playwright connects to."""
        if not self.browser_auth:
            raise ScraperConfigError(
                "Scraping Browser not configured: set BRIGHTDATA_BROWSER_AUTH "
                "(format 'brd-customer-<id>-zone-<zone>:<password>')."
            )
        return f"wss://{self.browser_auth}@{self.browser_host}:{self.browser_port}"

    def require_browser(self) -> None:
        # Triggers the same validation as browser_cdp_url, with a clear error.
        _ = self.browser_cdp_url

    def require_unlocker(self) -> None:
        missing = [
            name
            for name, val in (
                ("BRIGHTDATA_API_TOKEN", self.api_token),
                ("BRIGHTDATA_UNLOCKER_ZONE", self.unlocker_zone),
            )
            if not val
        ]
        if missing:
            raise ScraperConfigError(
                "Web Unlocker not configured: set " + ", ".join(missing)
            )


@dataclass
class ScraperConfig:
    bright_data: BrightDataConfig
    # Gemini model used for extraction. flash-lite matches the project's agent
    # and keeps per-page cost low; override for higher accuracy.
    extraction_model: str = "gemini-2.5-flash-lite"
    # Browser behaviour / cost controls.
    block_resources: tuple[str, ...] = DEFAULT_BLOCKED_RESOURCES
    page_timeout_ms: int = 60_000
    nav_wait_until: str = "domcontentloaded"
    # Cap HTML sent to the LLM (chars) to bound token cost on huge pages.
    max_html_chars: int = 400_000
    # Politeness: delay between page fetches within a run (seconds).
    page_delay: float = 1.0
    default_max_pages: int = 1
    # When using the local browser (BRIGHTDATA_USE=false), run headless?
    # Default is HEADED (visible) — gated SPAs (avasam) need it, and it's the
    # current preference. Set LOCAL_BROWSER_HEADLESS=true to run hidden.
    # Ignored by the Bright Data transport.
    local_browser_headless: bool = False
    # Default cap on how many products get detail-page enrichment when
    # enrich=True and no explicit max_enrich is given. Each enriched product
    # costs one extra page fetch + one extra Gemini call, so keep this modest
    # for cost control. Pass max_enrich=0 to a scrape call to enrich every
    # product found (no cap).
    default_max_enrich: int = 10

    @classmethod
    def from_env(cls, **overrides: object) -> "ScraperConfig":
        cfg = cls(bright_data=BrightDataConfig.from_env())
        model = os.getenv("GEMINI_EXTRACTION_MODEL")
        if model:
            cfg.extraction_model = model
        headless_val = os.getenv("LOCAL_BROWSER_HEADLESS", "false").strip().lower()
        cfg.local_browser_headless = headless_val in ("true", "1", "yes", "on")
        for key, value in overrides.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg
