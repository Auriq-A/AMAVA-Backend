"""FBA Inventory API (v1).

Real-time stock levels in Amazon's fulfillment network.
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class FBAInventoryAPI(BaseSection):
    path_prefix = "/fba/inventory/v1"

    def get_inventory_summaries(
        self,
        *,
        marketplace_ids: list[str] | None = None,
        details: bool = False,
        granularity_type: str = "Marketplace",
        granularity_id: str | None = None,
        start_date_time: str | None = None,
        seller_skus: list[str] | None = None,
        seller_sku: str | None = None,
        next_token: str | None = None,
    ) -> SPAPIResponse:
        """Summarize FBA inventory. Operation: getInventorySummaries.

        ``granularity_id`` defaults to the configured marketplace id, which is
        what Amazon expects when granularity_type is "Marketplace".
        """
        mp_ids = self._default_marketplace_ids(marketplace_ids)
        params = {
            "marketplaceIds": mp_ids,
            "details": details,
            "granularityType": granularity_type,
            "granularityId": granularity_id or mp_ids[0],
            "startDateTime": start_date_time,
            "sellerSkus": seller_skus,
            "sellerSku": seller_sku,
            "nextToken": next_token,
        }
        return self._get(
            "/summaries", operation="getInventorySummaries", params=params
        )
