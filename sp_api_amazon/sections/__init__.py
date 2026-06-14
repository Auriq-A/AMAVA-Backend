"""API section classes, one per SP-API.

Each is exposed as an attribute on the AmazonSPAPI facade (sp.orders, sp.catalog
...). To add a new API, create a module here following the BaseSection pattern
and wire it into AmazonSPAPI.__init__.
"""
from .base import BaseSection
from .catalog import CatalogItemsAPI
from .fba_inventory import FBAInventoryAPI
from .feeds import FeedsAPI
from .listings import ListingsItemsAPI
from .orders import OrdersAPI
from .pricing import ProductPricingAPI
from .product_types import ProductTypeDefinitionsAPI
from .reports import ReportsAPI
from .sales import SalesAPI
from .sellers import SellersAPI
from .tokens import TokensAPI

__all__ = [
    "BaseSection",
    "CatalogItemsAPI",
    "FBAInventoryAPI",
    "FeedsAPI",
    "ListingsItemsAPI",
    "OrdersAPI",
    "ProductPricingAPI",
    "ProductTypeDefinitionsAPI",
    "ReportsAPI",
    "SalesAPI",
    "SellersAPI",
    "TokensAPI",
]
