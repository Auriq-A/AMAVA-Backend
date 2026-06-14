"""Product Type Definitions API (2020-09-01).

Fetch the attribute schema for a product type - used to build valid bodies for
Listings Items put/patch calls.
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class ProductTypeDefinitionsAPI(BaseSection):
    path_prefix = "/definitions/2020-09-01"

    def search_definitions_product_types(
        self,
        *,
        keywords: list[str] | None = None,
        marketplace_ids: list[str] | None = None,
        item_name: str | None = None,
        locale: str | None = None,
        search_locale: str | None = None,
    ) -> SPAPIResponse:
        """Find product types by keyword. Operation: searchDefinitionsProductTypes."""
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "keywords": keywords,
            "itemName": item_name,
            "locale": locale,
            "searchLocale": search_locale,
        }
        return self._get(
            "/productTypes",
            operation="searchDefinitionsProductTypes",
            params=params,
        )

    def get_definitions_product_type(
        self,
        product_type: str,
        *,
        marketplace_ids: list[str] | None = None,
        requirements: str | None = None,
        requirements_enforced: str | None = None,
        locale: str | None = None,
    ) -> SPAPIResponse:
        """Get the schema for a single product type.
        Operation: getDefinitionsProductType."""
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "requirements": requirements,
            "requirementsEnforced": requirements_enforced,
            "locale": locale,
        }
        return self._get(
            f"/productTypes/{product_type}",
            operation="getDefinitionsProductType",
            params=params,
        )
