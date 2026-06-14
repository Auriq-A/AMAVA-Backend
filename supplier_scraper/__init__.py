"""AMAVA supplier scraper.

Scrapes wholesaler / supplier / distributor sites via Bright Data, then uses
Gemini to extract structured products from any layout.

    from supplier_scraper import SupplierScraper

    scraper = SupplierScraper()                          # reads env
    result = await scraper.scrape_supplier("avasam", max_pages=5)
    for p in result.products:
        print(p.sku, p.title, p.price)

Transports (chosen automatically per supplier):
  * Scraping Browser - gated/interactive sites (login, JS, click pagination).
  * Web Unlocker     - public/static catalogs (cheaper, stateless).

Construction performs no network and needs no API keys; transports/extractor
connect lazily on first use.

Environment (see .env.example):
  Bright Data:  BRIGHTDATA_BROWSER_AUTH, BRIGHTDATA_API_TOKEN,
                BRIGHTDATA_UNLOCKER_ZONE
  Gemini:       GOOGLE_API_KEY (already used by the project's ADK agent)
  Supplier creds: per-profile, e.g. AVASAM_EMAIL / AVASAM_PASSWORD
"""
from __future__ import annotations

from .config import BrightDataConfig, ScraperConfig
from .exceptions import (
    ExtractionError,
    LoginError,
    ScraperConfigError,
    ScraperError,
    TransportError,
)
from .extraction import Extractor, GeminiExtractor, clean_html
from .models import (
    LoginConfig,
    PaginationConfig,
    Product,
    ScrapeResult,
    SupplierProfile,
)
from .scraper import SupplierScraper
from .suppliers import SUPPLIERS, get_supplier, register

__version__ = "0.1.0"

__all__ = [
    "SupplierScraper",
    # config
    "ScraperConfig",
    "BrightDataConfig",
    # models
    "Product",
    "ScrapeResult",
    "SupplierProfile",
    "LoginConfig",
    "PaginationConfig",
    # extraction
    "Extractor",
    "GeminiExtractor",
    "clean_html",
    # suppliers
    "SUPPLIERS",
    "get_supplier",
    "register",
    # errors
    "ScraperError",
    "ScraperConfigError",
    "TransportError",
    "LoginError",
    "ExtractionError",
]
