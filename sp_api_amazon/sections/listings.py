"""Listings Items API (2021-08-01).

Create, update, fetch and delete the seller's own listings. These operations
key on the selling-partner id (seller id), which defaults to the configured
``seller_id`` (env SPAPI_SELLER_ID) but can be passed per call.

``delete_listings_item`` is what the brief called "removeListing".
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIResponse
from ..exceptions import SPAPIConfigError
from .base import BaseSection


class ListingsItemsAPI(BaseSection):
    path_prefix = "/listings/2021-08-01"

    def _seller(self, seller_id: str | None) -> str:
        sid = seller_id or self._client.config.seller_id
        if not sid:
            raise SPAPIConfigError(
                "Listings operations need a seller_id. Pass seller_id=... or set "
                "SPAPI_SELLER_ID in the environment."
            )
        return sid

    def get_listings_item(
        self,
        sku: str,
        *,
        seller_id: str | None = None,
        marketplace_ids: list[str] | None = None,
        included_data: list[str] | None = None,
        issue_locale: str | None = None,
    ) -> SPAPIResponse:
        """Fetch one of the seller's listings by SKU. Operation: getListingsItem."""
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "includedData": included_data,
            "issueLocale": issue_locale,
        }
        return self._get(
            f"/items/{self._seller(seller_id)}/{sku}",
            operation="getListingsItem",
            params=params,
        )

    def put_listings_item(
        self,
        sku: str,
        *,
        product_type: str,
        attributes: dict[str, Any],
        requirements: str | None = None,
        seller_id: str | None = None,
        marketplace_ids: list[str] | None = None,
        issue_locale: str | None = None,
    ) -> SPAPIResponse:
        """Create or fully replace a listing. Operation: putListingsItem."""
        body: dict[str, Any] = {"productType": product_type, "attributes": attributes}
        if requirements is not None:
            body["requirements"] = requirements
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "issueLocale": issue_locale,
        }
        return self._put(
            f"/items/{self._seller(seller_id)}/{sku}",
            operation="putListingsItem",
            params=params,
            json_body=body,
        )

    def patch_listings_item(
        self,
        sku: str,
        *,
        product_type: str,
        patches: list[dict[str, Any]],
        seller_id: str | None = None,
        marketplace_ids: list[str] | None = None,
        issue_locale: str | None = None,
    ) -> SPAPIResponse:
        """Partially update a listing (JSON Patch). Operation: patchListingsItem."""
        body = {"productType": product_type, "patches": patches}
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "issueLocale": issue_locale,
        }
        return self._patch(
            f"/items/{self._seller(seller_id)}/{sku}",
            operation="patchListingsItem",
            params=params,
            json_body=body,
        )

    def delete_listings_item(
        self,
        sku: str,
        *,
        seller_id: str | None = None,
        marketplace_ids: list[str] | None = None,
        issue_locale: str | None = None,
    ) -> SPAPIResponse:
        """Delete a listing by SKU ("removeListing"). Operation: deleteListingsItem."""
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "issueLocale": issue_locale,
        }
        return self._delete(
            f"/items/{self._seller(seller_id)}/{sku}",
            operation="deleteListingsItem",
            params=params,
        )
