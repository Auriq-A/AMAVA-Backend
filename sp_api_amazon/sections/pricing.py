"""Product Pricing API (v0).

Competitive pricing and offer listings - the data behind repricing and
margin/competitive-analysis decisions.
"""
from __future__ import annotations

from ..client import SPAPIResponse
from .base import BaseSection


class ProductPricingAPI(BaseSection):
    path_prefix = "/products/pricing/v0"

    def get_pricing(
        self,
        *,
        item_type: str,
        asins: list[str] | None = None,
        skus: list[str] | None = None,
        marketplace_id: str | None = None,
        item_condition: str | None = None,
        offer_type: str | None = None,
    ) -> SPAPIResponse:
        """Get the seller's prices for a set of ASINs or SKUs.
        Operation: getPricing. ``item_type`` is "Asin" or "Sku"."""
        params = {
            "MarketplaceId": marketplace_id or self.marketplace_id,
            "ItemType": item_type,
            "Asins": asins,
            "Skus": skus,
            "ItemCondition": item_condition,
            "OfferType": offer_type,
        }
        return self._get("/price", operation="getPricing", params=params)

    def get_competitive_pricing(
        self,
        *,
        item_type: str,
        asins: list[str] | None = None,
        skus: list[str] | None = None,
        marketplace_id: str | None = None,
        customer_type: str | None = None,
    ) -> SPAPIResponse:
        """Get competitive pricing for ASINs/SKUs. Operation: getCompetitivePricing."""
        params = {
            "MarketplaceId": marketplace_id or self.marketplace_id,
            "ItemType": item_type,
            "Asins": asins,
            "Skus": skus,
            "CustomerType": customer_type,
        }
        return self._get(
            "/competitivePrice", operation="getCompetitivePricing", params=params
        )

    def get_item_offers(
        self,
        asin: str,
        *,
        item_condition: str,
        marketplace_id: str | None = None,
        customer_type: str | None = None,
    ) -> SPAPIResponse:
        """Get the lowest offers for an ASIN. Operation: getItemOffers."""
        params = {
            "MarketplaceId": marketplace_id or self.marketplace_id,
            "ItemCondition": item_condition,
            "CustomerType": customer_type,
        }
        return self._get(
            f"/items/{asin}/offers", operation="getItemOffers", params=params
        )

    def get_listing_offers(
        self,
        sku: str,
        *,
        item_condition: str,
        marketplace_id: str | None = None,
        customer_type: str | None = None,
    ) -> SPAPIResponse:
        """Get the lowest offers for one of the seller's SKUs.
        Operation: getListingOffers."""
        params = {
            "MarketplaceId": marketplace_id or self.marketplace_id,
            "ItemCondition": item_condition,
            "CustomerType": customer_type,
        }
        return self._get(
            f"/listings/{sku}/offers", operation="getListingOffers", params=params
        )
