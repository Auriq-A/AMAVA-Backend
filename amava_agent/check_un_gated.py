"""Seller-specific Amazon listing eligibility checks.

This replaces the legacy Check_Un_Gated.py script with reusable logic that
uses the signed-in user's SP-API client. It performs no file I/O and contains
no credentials, seller IDs, or marketplace IDs.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any


_ASIN_RE = re.compile(r"^[A-Z0-9]{10}$", re.IGNORECASE)
_PLACEHOLDERS = {
    "", "UPC", "EAN", "ASIN", "SKU", "NO BARCODE", "NO BAR CODE",
    "MIXED", "N/A", "NA", "NONE",
}


def _payload(response: Any) -> dict[str, Any]:
    payload = getattr(response, "payload", response)
    return payload if isinstance(payload, dict) else {}


class AmazonEligibilityChecker:
    """Resolve product keys to ASINs and check Listings Restrictions."""

    def __init__(self, spapi: Any) -> None:
        self.sp = spapi
        self.seller_id = getattr(spapi.config, "seller_id", None)
        self.marketplace_id = spapi.config.marketplace.marketplace_id
        if not self.seller_id:
            raise ValueError(
                "Amazon seller_id is required for gated/ungated checks. "
                "Reconnect SP-API with the Seller ID filled in."
            )

    def resolve_asin(self, value: str, *, unit: str = "search_key") -> str | None:
        key = str(value).strip()
        if not key or key.upper() in _PLACEHOLDERS:
            return None

        mode = unit.strip().lower().replace("-", "_").replace(" ", "_")
        if mode == "asin":
            return key.upper() if _ASIN_RE.fullmatch(key) else None

        identifier_type = _identifier_type(key, mode)
        if identifier_type == "ASIN":
            return key.upper()
        if identifier_type:
            response = self.sp.catalog.search_catalog_items(
                identifiers=[key],
                identifiers_type=identifier_type,
                marketplace_ids=[self.marketplace_id],
                page_size=1,
            )
        else:
            response = self.sp.catalog.search_catalog_items(
                keywords=[key],
                marketplace_ids=[self.marketplace_id],
                page_size=1,
            )
        items = _payload(response).get("items") or []
        if not items or not isinstance(items[0], dict):
            return None
        asin = items[0].get("asin")
        return str(asin).upper() if asin else None

    def check_one(
        self,
        value: str,
        *,
        unit: str = "search_key",
        condition_type: str = "new_new",
    ) -> dict[str, Any] | None:
        asin = self.resolve_asin(value, unit=unit)
        if not asin:
            return None
        response = self.sp.restrictions.get_listings_restrictions(
            asin,
            seller_id=self.seller_id,
            marketplace_ids=[self.marketplace_id],
            condition_type=condition_type,
        )
        restrictions = list(_payload(response).get("restrictions") or [])
        details = _restriction_details(restrictions)
        eligibility, approval_required, status = _classify(details)
        return {
            "productASIN": asin,
            "status": status,
            "eligibility": eligibility,
            "approval_required": approval_required,
            "restrictions": restrictions,
            "reason_codes": [d["reason_code"] for d in details if d["reason_code"]],
            "messages": [d["message"] for d in details if d["message"]],
        }

    def check_many(
        self,
        values: Iterable[str],
        *,
        unit: str = "search_key",
        condition_type: str = "new_new",
        progress: Callable[[int, int, dict[str, Any] | None], None] | None = None,
    ) -> dict[str, Any]:
        keys = [str(v).strip() for v in values if str(v).strip()]
        results: dict[str, list[dict[str, Any]]] = {}
        skipped: list[dict[str, str]] = []
        summary = {"total": len(keys), "ungated": 0, "gated": 0, "errors": 0}

        for index, key in enumerate(keys, 1):
            item: dict[str, Any] | None = None
            try:
                item = self.check_one(key, unit=unit, condition_type=condition_type)
                if item is None:
                    skipped.append({"productUPC": key, "reason": "No ASIN found"})
                else:
                    results.setdefault(key, []).append(item)
                    summary[item["eligibility"]] += 1
            except Exception as exc:  # keep a batch moving after one bad item
                skipped.append({"productUPC": key, "reason": str(exc)})
                summary["errors"] += 1
            if progress:
                progress(index, len(keys), item)

        summary["skipped"] = len(skipped)
        summary["checked"] = summary["ungated"] + summary["gated"]
        return {"results": results, "skipped": skipped, "summary": summary, "unit": unit}


def _identifier_type(key: str, mode: str) -> str | None:
    explicit = {
        "upc": "UPC", "ean": "EAN", "isbn": "ISBN", "jan": "JAN",
        "gtin": "GTIN", "asin": "ASIN", "title": None, "keyword": None,
        "keywords": None,
    }
    if mode in explicit:
        return explicit[mode]

    # Auto mode. X00... values are commonly FNSKUs, not ASINs.
    if _ASIN_RE.fullmatch(key) and not key.upper().startswith("X00") and any(
        c.isalpha() for c in key
    ):
        return "ASIN"
    if key.isdigit():
        return {8: "GTIN", 10: "ISBN", 12: "UPC", 13: "EAN", 14: "GTIN"}.get(
            len(key)
        )
    return None


def _restriction_details(restrictions: list[Any]) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for restriction in restrictions:
        if not isinstance(restriction, dict):
            continue
        reasons = restriction.get("reasons") or []
        if not reasons:
            details.append({"reason_code": "RESTRICTED", "message": "Listing restricted"})
            continue
        for reason in reasons:
            if not isinstance(reason, dict):
                continue
            details.append({
                "reason_code": str(reason.get("reasonCode") or "").upper(),
                "message": str(reason.get("message") or "").strip(),
            })
    return details


def _classify(details: list[dict[str, str]]) -> tuple[str, bool, str]:
    if not details:
        return "ungated", False, "You can sell this item."

    codes = {d["reason_code"] for d in details}
    messages = [d["message"] for d in details if d["message"]]
    suffix = f" {'; '.join(messages)}" if messages else ""
    if "APPROVAL_REQUIRED" in codes:
        return "gated", True, f"Approval is required to sell this item.{suffix}"
    if "NOT_ELIGIBLE" in codes:
        return "gated", False, f"You are not eligible to sell this item.{suffix}"
    return "gated", False, f"This item has listing restrictions.{suffix}"
