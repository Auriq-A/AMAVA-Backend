"""Data models for scraping: what we extract, and how a supplier is described.

These are plain dataclasses (no pydantic dependency). ``Product`` is the
normalized output; ``SupplierProfile`` + its sub-configs describe how to scrape
one supplier (login, pagination, transport choice).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------
@dataclass
class Product:
    """A single product extracted from a supplier page. Most fields are
    optional - the LLM fills what it can find for a given site.

    ``description``, ``images``, ``specifications``, ``rating`` and
    ``stock_quantity`` are typically only available from a product's detail
    page - see ``merge_detail()`` and ``SupplierScraper``'s ``enrich`` option.
    """

    title: str | None = None
    sku: str | None = None
    price: float | None = None
    currency: str | None = None
    moq: int | None = None              # minimum order quantity
    in_stock: bool | None = None
    stock_quantity: int | None = None   # exact stock count, if shown
    brand: str | None = None
    upc: str | None = None
    ean: str | None = None
    product_url: str | None = None
    image_url: str | None = None
    images: list[str] = field(default_factory=list)        # gallery images
    category: str | None = None
    description: str | None = None      # full description (detail page)
    specifications: dict[str, str] = field(default_factory=dict)  # spec table
    rating: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # anything site-specific

    # Fields where a value already known from the listing page wins; a
    # detail-page extraction only fills in gaps for these.
    _SCALAR_FIELDS = (
        "title", "sku", "price", "currency", "moq", "in_stock", "brand",
        "upc", "ean", "product_url", "image_url", "category",
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def merge_detail(self, detail: "Product") -> None:
        """Fold in a detail-page extraction without clobbering values already
        known from the listing page.

        - Scalar listing fields (title, price, brand, ...) are filled only if
          currently empty.
        - Detail-only fields (description, rating, stock_quantity) are taken
          from ``detail`` whenever present.
        - ``images`` and ``specifications`` are merged/extended.
        - ``extra`` keys from ``detail`` are added without overwriting
          existing keys.
        """
        for f in self._SCALAR_FIELDS:
            if getattr(self, f) in (None, "") and getattr(detail, f) not in (None, ""):
                setattr(self, f, getattr(detail, f))

        for f in ("stock_quantity", "rating", "description"):
            value = getattr(detail, f)
            if value not in (None, ""):
                setattr(self, f, value)

        if detail.images:
            seen = set(self.images)
            for url in detail.images:
                if url and url not in seen:
                    self.images.append(url)
                    seen.add(url)

        if detail.specifications:
            self.specifications.update(detail.specifications)

        for k, v in detail.extra.items():
            self.extra.setdefault(k, v)


@dataclass
class ScrapeResult:
    """The outcome of scraping one supplier/URL run."""

    source: str                      # supplier name or starting URL
    products: list[Product] = field(default_factory=list)
    pages_scraped: int = 0
    transport_used: str | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.products)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "count": self.count,
            "pages_scraped": self.pages_scraped,
            "transport_used": self.transport_used,
            "errors": self.errors,
            "metadata": self.metadata,
            "products": [p.to_dict() for p in self.products],
        }


# ---------------------------------------------------------------------------
# Supplier description
# ---------------------------------------------------------------------------
@dataclass
class LoginConfig:
    """Declarative login flow for a gated supplier site.

    Credentials are read from environment variables (never hard-coded) named by
    ``username_env`` / ``password_env``.
    """

    url: str
    username_selector: str
    password_selector: str
    submit_selector: str
    username_env: str
    password_env: str
    success_selector: str | None = None     # element proving login succeeded
    wait_after_ms: int = 1500


@dataclass
class PaginationConfig:
    """How to walk multiple pages of a catalog.

    strategy:
      * "none"        - single page only
      * "query"       - append/increment a query param (?page=N); works with any
                        transport, including the stateless Web Unlocker
      * "next_button" - click a "next" element; requires the browser transport
    """

    strategy: str = "none"
    page_param: str = "page"
    start_page: int = 1
    next_selector: str | None = None
    max_pages: int = 1


@dataclass
class SupplierProfile:
    """Everything needed to scrape one supplier."""

    name: str
    base_url: str
    requires_login: bool = False
    # "auto" -> browser if login required else unlocker; or force "browser"/"unlocker".
    transport: str = "auto"
    login: LoginConfig | None = None
    pagination: PaginationConfig = field(default_factory=PaginationConfig)
    # Optional natural-language hint passed to the extractor about this site's
    # fields/quirks (e.g. "prices are per-case; MOQ shown as 'Min Qty'").
    extraction_hint: str = ""
    # CSS selector to wait for before reading the page (ensures JS rendered).
    wait_for: str | None = None
    # CSS selector to wait for on a PRODUCT DETAIL page before reading it
    # (used by the optional enrichment step). SPA sites (e.g. avasam) render
    # an empty shell until JS populates this; static/SSR sites can leave it
    # as None.
    detail_wait_for: str | None = None

    def resolve_transport(self) -> str:
        if self.transport != "auto":
            return self.transport
        return "browser" if self.requires_login else "unlocker"
