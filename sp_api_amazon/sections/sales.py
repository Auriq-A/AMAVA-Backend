"""Sales API (v1).

Aggregated order metrics over a time interval - feeds the analytics layer
(revenue, units, average order value over time).
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class SalesAPI(BaseSection):
    path_prefix = "/sales/v1"

    def get_order_metrics(
        self,
        *,
        interval: str,
        granularity: str,
        marketplace_ids: list[str] | None = None,
        granularity_time_zone: str | None = None,
        buyer_type: str | None = None,
        fulfillment_network: str | None = None,
        first_day_of_week: str | None = None,
        asin: str | None = None,
        sku: str | None = None,
    ) -> SPAPIResponse:
        """Aggregated order metrics. Operation: getOrderMetrics.

        ``interval`` is an ISO 8601 range, e.g.
        "2024-01-01T00:00:00-08:00--2024-01-31T23:59:59-08:00".
        ``granularity`` is one of Hour/Day/Week/Month/Year/Total. When it is not
        Total, ``granularity_time_zone`` is required.
        """
        params = {
            "marketplaceIds": self._default_marketplace_ids(marketplace_ids),
            "interval": interval,
            "granularity": granularity,
            "granularityTimeZone": granularity_time_zone,
            "buyerType": buyer_type,
            "fulfillmentNetwork": fulfillment_network,
            "firstDayOfWeek": first_day_of_week,
            "asin": asin,
            "sku": sku,
        }
        return self._get(
            "/orderMetrics", operation="getOrderMetrics", params=params
        )
