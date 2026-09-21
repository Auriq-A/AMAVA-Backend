"""Product Fees API (v0)."""
from __future__ import annotations

import uuid

from ..client import SPAPIResponse
from .base import BaseSection


class ProductFeesAPI(BaseSection):
    path_prefix = "/products/fees/v0"

    def get_my_fees_estimate_for_asin(
        self,
        asin: str,
        *,
        price: float,
        currency_code: str,
        is_amazon_fulfilled: bool,
        marketplace_id: str | None = None,
        shipping_price: float = 0.0,
        identifier: str | None = None,
    ) -> SPAPIResponse:
        """Estimate Amazon fees for one ASIN at a proposed price."""
        price_to_estimate: dict[str, dict[str, str | float]] = {
            "ListingPrice": {
                "CurrencyCode": currency_code,
                "Amount": float(price),
            }
        }
        if shipping_price:
            price_to_estimate["Shipping"] = {
                "CurrencyCode": currency_code,
                "Amount": float(shipping_price),
            }

        body = {
            "FeesEstimateRequest": {
                "MarketplaceId": marketplace_id or self.marketplace_id,
                "IsAmazonFulfilled": bool(is_amazon_fulfilled),
                "PriceToEstimateFees": price_to_estimate,
                "Identifier": identifier or str(uuid.uuid4()),
            }
        }
        return self._post(
            f"/items/{asin}/feesEstimate",
            operation="getMyFeesEstimateForASIN",
            json_body=body,
        )
