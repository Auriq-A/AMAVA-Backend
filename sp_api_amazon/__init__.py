"""AMAVA Amazon SP-API client.

A lean, dependency-light OOP wrapper over the Amazon Selling Partner API.
Import the facade, construct it once, and call grouped operations:

    from sp_api_amazon import AmazonSPAPI

    sp = AmazonSPAPI()                      # reads creds from the environment
    sp.sellers.get_marketplace_participations()
    sp.orders.get_orders(created_after="2024-01-01T00:00:00Z")
    sp.catalog.search_catalog_items(keywords=["usb cable"])
    sp.listings.delete_listings_item(sku="MY-SKU-1")   # "removeListing"

Operations are grouped by API (sp.orders, sp.listings, sp.catalog, ...) rather
than flattened onto one object, to avoid name collisions and keep each API
independently discoverable. The constructor makes no network calls; tokens are
fetched lazily on the first request.

Required environment variables (prefix SPAPI_):
    SPAPI_LWA_CLIENT_ID, SPAPI_LWA_CLIENT_SECRET, SPAPI_REFRESH_TOKEN
Optional:
    SPAPI_MARKETPLACE (default "US"), SPAPI_SELLER_ID, SPAPI_SANDBOX,
    SPAPI_AWS_ACCESS_KEY_ID / SPAPI_AWS_SECRET_ACCESS_KEY (only if use_sigv4)
"""
from __future__ import annotations

from .client import SPAPIClient, SPAPIResponse
from .config import Credentials, SPAPIConfig
from .exceptions import (
    SPAPIAuthError,
    SPAPIConfigError,
    SPAPIError,
    SPAPINotFoundError,
    SPAPIServerError,
    SPAPIThrottledError,
    SPAPIValidationError,
)
from .marketplaces import Marketplace, Region, resolve_marketplace
from .sections import (
    CatalogItemsAPI,
    FBAInventoryAPI,
    FeedsAPI,
    ListingsItemsAPI,
    OrdersAPI,
    ProductPricingAPI,
    ProductTypeDefinitionsAPI,
    ReportsAPI,
    SalesAPI,
    SellersAPI,
    TokensAPI,
)

__version__ = "0.1.0"


class AmazonSPAPI:
    """Top-level entry point. Composes one instance of each API section over a
    shared client (single token cache + rate limiter)."""

    def __init__(
        self,
        credentials: Credentials | None = None,
        *,
        marketplace: str | Marketplace = "US",
        region: str | Region | None = None,
        sandbox: bool = False,
        use_sigv4: bool = False,
        seller_id: str | None = None,
        config: SPAPIConfig | None = None,
        **tunables: object,
    ) -> None:
        if config is None:
            config = SPAPIConfig.resolve(
                credentials,
                marketplace=marketplace,
                region=region,
                sandbox=sandbox,
                use_sigv4=use_sigv4,
                **tunables,
            )
            if seller_id is not None:
                config.seller_id = seller_id
        self.config = config
        self.client = SPAPIClient(config)

        # API sections.
        self.sellers = SellersAPI(self.client)
        self.orders = OrdersAPI(self.client)
        self.inventory = FBAInventoryAPI(self.client)
        self.listings = ListingsItemsAPI(self.client)
        self.catalog = CatalogItemsAPI(self.client)
        self.pricing = ProductPricingAPI(self.client)
        self.product_types = ProductTypeDefinitionsAPI(self.client)
        self.reports = ReportsAPI(self.client)
        self.feeds = FeedsAPI(self.client)
        self.sales = SalesAPI(self.client)
        self.tokens = TokensAPI(self.client)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        mp = self.config.marketplace
        mode = "sandbox" if self.config.sandbox else "production"
        return f"<AmazonSPAPI marketplace={mp.name} region={mp.region.code} {mode}>"


__all__ = [
    "AmazonSPAPI",
    "Credentials",
    "SPAPIConfig",
    "SPAPIClient",
    "SPAPIResponse",
    "Marketplace",
    "Region",
    "resolve_marketplace",
    # Errors
    "SPAPIError",
    "SPAPIConfigError",
    "SPAPIAuthError",
    "SPAPIThrottledError",
    "SPAPINotFoundError",
    "SPAPIValidationError",
    "SPAPIServerError",
]
