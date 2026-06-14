"""Catalog Items API (2022-04-01).

Search Amazon's catalog and fetch item details by ASIN - the basis for the
"check on Amazon" / competitive-analysis flows.
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class CatalogItemsAPI(BaseSection):
    path_prefix = "/catalog/2022-04-01"

    def search_catalog_items(
        self,
        *,
        keywords: list[str] | None = None,
        identifiers: list[str] | None = None,
        identifiers_type: str | None = None,
        marketplace_ids: list[str] | None = None,
        included_data: list[str] | None = None,
        brand_names: list[str] | None = None,
        classification_ids: list[str] | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        locale: str | None = None,
        seller_id: str | None = None,
    ) -> SPAPIResponse:
        """Search the catalog by keyword or identifier (UPC/EAN/ASIN/...).
        Operation: searchCatalogItems.

        Provide either ``keywords`` or ``identifiers`` (+ ``identifiers_type``).
        """
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "keywords": keywords,
            "identifiers": identifiers,
            "identifiersType": identifiers_type,
            "includedData": included_data,
            "brandNames": brand_names,
            "classificationIds": classification_ids,
            "pageSize": page_size,
            "pageToken": page_token,
            "locale": locale,
            "sellerId": seller_id,
        }
        return self._get("/items", operation="searchCatalogItems", params=params)

    def get_catalog_item(
        self,
        asin: str,
        *,
        marketplace_ids: list[str] | None = None,
        included_data: list[str] | None = None,
        locale: str | None = None,
    ) -> SPAPIResponse:
        """Get catalog details for one ASIN. Operation: getCatalogItem."""
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "includedData": included_data,
            "locale": locale,
        }
        return self._get(
            f"/items/{asin}", operation="getCatalogItem", params=params
        )
