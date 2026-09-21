"""Listings Restrictions API (2021-08-01)."""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class ListingsRestrictionsAPI(BaseSection):
    """Seller-specific catalog listing eligibility checks."""

    path_prefix = "/listings/2021-08-01"

    def get_listings_restrictions(
        self,
        asin: str,
        *,
        seller_id: str | None = None,
        marketplace_ids: list[str] | None = None,
        condition_type: str = "new_new",
        reason_locale: str | None = "en_US",
    ) -> SPAPIResponse:
        """Return listing restrictions for an ASIN and selling account."""
        resolved_seller = seller_id or self._client.config.seller_id
        if not resolved_seller:
            raise ValueError(
                "seller_id is required for Listings Restrictions. Save it with "
                "the user's Amazon SP-API credentials."
            )
        return self._get(
            "/restrictions",
            operation="getListingsRestrictions",
            params={
                "asin": asin,
                "sellerId": resolved_seller,
                "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
                "conditionType": condition_type,
                "reasonLocale": reason_locale,
            },
        )
