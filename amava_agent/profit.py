"""Reusable FBA and FBM single-product profit calculations."""
from __future__ import annotations

import re
from typing import Any


_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_CURRENCIES = {
    "US": "USD", "CA": "CAD", "MX": "MXN", "BR": "BRL", "UK": "GBP",
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", "NL": "EUR",
    "BE": "EUR", "SE": "SEK", "PL": "PLN", "TR": "TRY", "AE": "AED",
    "SA": "SAR", "EG": "EGP", "IN": "INR", "JP": "JPY", "AU": "AUD",
    "SG": "SGD",
}


def _payload(response: Any) -> dict[str, Any]:
    payload = getattr(response, "payload", response)
    return payload if isinstance(payload, dict) else {}


class AmazonProfitCalculator:
    """Get a channel-specific offer, estimate fees, and calculate profit."""

    def __init__(self, spapi: Any) -> None:
        self.sp = spapi
        self.marketplace = spapi.config.marketplace

    def calculate(
        self,
        asin: str,
        cost: float,
        *,
        fulfillment: str,
        price: float | None = None,
        customer_shipping: float = 0.0,
        shipping_cost: float = 0.0,
        other_costs: float = 0.0,
        currency_code: str | None = None,
    ) -> dict[str, Any]:
        asin = asin.strip().upper()
        if not _ASIN_RE.fullmatch(asin):
            raise ValueError("asin must be a 10-character Amazon ASIN")
        mode = fulfillment.strip().upper()
        if mode not in {"FBA", "FBM"}:
            raise ValueError("fulfillment must be FBA or FBM")
        for name, value in {
            "cost": cost, "price": price, "customer_shipping": customer_shipping,
            "shipping_cost": shipping_cost, "other_costs": other_costs,
        }.items():
            if value is not None and float(value) < 0:
                raise ValueError(f"{name} cannot be negative")

        source = "manual"
        if price is None:
            offer = self._lowest_offer(asin, mode)
            price = offer["listing_price"]
            customer_shipping = offer["customer_shipping"]
            currency_code = currency_code or offer["currency"]
            source = "lowest_offer"
        currency_code = currency_code or _CURRENCIES.get(self.marketplace.name, "USD")

        fee_data = self._fees(
            asin,
            float(price),
            float(customer_shipping),
            currency_code,
            is_amazon_fulfilled=mode == "FBA",
        )
        revenue = float(price) + float(customer_shipping)
        total_cost = float(cost) + float(shipping_cost) + float(other_costs)
        profit = revenue - fee_data["total_fee"] - total_cost
        invested = total_cost or float(cost)

        return {
            "status": "success",
            "asin": asin,
            "fulfillment": mode,
            "price_source": source,
            # Legacy clients treated price as the landed/customer price.
            "price": round(revenue, 2),
            "listing_price": round(float(price), 2),
            "customer_shipping": round(float(customer_shipping), 2),
            "currency": currency_code,
            "fees": round(fee_data["total_fee"], 2),
            "total_fees": round(fee_data["total_fee"], 2),
            "fulfillment_fee": round(fee_data["fulfillment_fee"], 2),
            "fee_breakdown": fee_data["breakdown"],
            "cost": round(float(cost), 2),
            "shipping_cost": round(float(shipping_cost), 2),
            "other_costs": round(float(other_costs), 2),
            "profit": round(profit, 2),
            "margin_percent": round((profit / revenue * 100) if revenue else 0.0, 2),
            "roi_percent": round((profit / invested * 100) if invested else 0.0, 2),
        }

    def _lowest_offer(self, asin: str, mode: str) -> dict[str, Any]:
        response = self.sp.pricing.get_item_offers(asin, item_condition="New")
        summary = _payload(response).get("Summary") or {}
        lowest_prices = summary.get("LowestPrices") or []
        channel = "Amazon" if mode == "FBA" else "Merchant"
        candidates: list[dict[str, Any]] = []
        for offer in lowest_prices:
            if not isinstance(offer, dict) or offer.get("fulfillmentChannel") != channel:
                continue
            listing = offer.get("ListingPrice") or {}
            shipping = offer.get("Shipping") or {}
            landed = offer.get("LandedPrice") or {}
            try:
                listing_amount = float(listing.get("Amount", 0) or 0)
                shipping_amount = float(shipping.get("Amount", 0) or 0)
                landed_amount = float(
                    landed.get("Amount", listing_amount + shipping_amount)
                    or listing_amount + shipping_amount
                )
            except (TypeError, ValueError):
                continue
            if landed_amount <= 0:
                continue
            candidates.append({
                "listing_price": listing_amount or max(landed_amount - shipping_amount, 0),
                "customer_shipping": shipping_amount,
                "landed_price": landed_amount,
                "currency": (
                    listing.get("CurrencyCode")
                    or landed.get("CurrencyCode")
                    or _CURRENCIES.get(self.marketplace.name, "USD")
                ),
            })
        if not candidates:
            raise ValueError(
                f"No New {mode} offers were returned for {asin}. "
                "Provide price manually to calculate without an offer lookup."
            )
        return min(candidates, key=lambda item: item["landed_price"])

    def _fees(
        self,
        asin: str,
        price: float,
        customer_shipping: float,
        currency_code: str,
        *,
        is_amazon_fulfilled: bool,
    ) -> dict[str, Any]:
        response = self.sp.fees.get_my_fees_estimate_for_asin(
            asin,
            price=price,
            shipping_price=customer_shipping,
            currency_code=currency_code,
            is_amazon_fulfilled=is_amazon_fulfilled,
        )
        payload = _payload(response)
        result = payload.get("FeesEstimateResult") or {}
        estimate = result.get("FeesEstimate") or {}
        total_money = estimate.get("TotalFeesEstimate") or {}
        try:
            total_fee = float(total_money["Amount"])
        except (KeyError, TypeError, ValueError) as exc:
            errors = result.get("Error") or payload.get("errors") or "missing fee total"
            raise ValueError(f"Amazon did not return a usable fee estimate: {errors}") from exc

        breakdown: list[dict[str, Any]] = []
        fulfillment_fee = 0.0
        for fee in estimate.get("FeeDetailList") or []:
            if not isinstance(fee, dict):
                continue
            amount = _money_amount(fee.get("FinalFee"))
            breakdown.append({"type": fee.get("FeeType", ""), "amount": round(amount, 2)})
            for included in fee.get("IncludedFeeList") or []:
                if not isinstance(included, dict):
                    continue
                included_amount = _money_amount(included.get("FinalFee"))
                breakdown.append({
                    "type": included.get("FeeType", ""),
                    "amount": round(included_amount, 2),
                })
                if included.get("FeeType") == "FBAPerUnitFulfillmentFee":
                    fulfillment_fee += included_amount
            if fee.get("FeeType") in {"FBAFees", "FBAPerUnitFulfillmentFee"} and not fee.get(
                "IncludedFeeList"
            ):
                fulfillment_fee += amount
        return {
            "total_fee": total_fee,
            "fulfillment_fee": fulfillment_fee,
            "breakdown": breakdown,
        }


def _money_amount(value: Any) -> float:
    if not isinstance(value, dict):
        return 0.0
    try:
        return float(value.get("Amount", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
