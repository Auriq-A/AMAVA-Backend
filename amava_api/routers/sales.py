"""Amazon SP-API endpoints — per-user, credentials from the encrypted vault.

Every endpoint resolves the acting user and builds their SP-API client via
``amava_agent.services.build_user_spapi`` (creds decrypted from the vault). If
the user hasn't connected Amazon yet, we return a clean 503 instead of doing
anything — so NOTHING here uses live SP-API until a user explicitly stores
credentials (honoring "SP-API later"). No keys are ever hardcoded.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from amava_agent.profit import AmazonProfitCalculator
from amava_agent.services import build_user_spapi

from ..deps import current_user_id, get_db
from ..store import AppStateStore

router = APIRouter(tags=["sales"])

_NOT_CONNECTED = JSONResponse(
    {
        "status": "error",
        "message": "Amazon SP-API not connected. Add your seller credentials "
        "in Connect Accounts.",
    },
    status_code=503,
)


def _client(user_id: int):
    """Return the user's SP-API client, or None if they have no creds."""
    try:
        return build_user_spapi(user_id)
    except ValueError:
        return None
    except Exception:  # noqa: BLE001 - missing sp_api package etc.
        return None


@router.get("/todays-sales")
async def todays_sales(user_id: int = Depends(current_user_id)):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    try:
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        resp = sp.orders.get_orders(created_after=start)
        orders = resp.get("Orders", []) or []
        sales_data = []
        for i, o in enumerate(orders, 1):
            total = o.get("OrderTotal") or {}
            sales_data.append({
                "id": i,
                "amazon_order_id": o.get("AmazonOrderId", ""),
                "purchase_date": o.get("PurchaseDate", ""),
                "order_status": o.get("OrderStatus", ""),
                "product_name": "",  # order-level; line items need getOrderItems
                "sku": "",
                "asin": "",
                "quantity": o.get("NumberOfItemsShipped", 0)
                or o.get("NumberOfItemsUnshipped", 0) or 0,
                "currency": total.get("CurrencyCode", "USD"),
                "item_price": float(total.get("Amount", 0) or 0),
                "ship_city": "",
                "ship_state": "",
                "ship_postal_code": "",
                "ship_country": (o.get("ShippingAddress") or {}).get("CountryCode", ""),
                "fulfillment_channel": o.get("FulfillmentChannel", ""),
                "sales_channel": o.get("SalesChannel", ""),
                "ship_service_level": o.get("ShipServiceLevel", ""),
            })
        return JSONResponse({"status": "success", "sales_data": sales_data})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=502)


@router.get("/sales-metrics")
async def sales_metrics(
    start_date: str = Query(...),
    end_date: str = Query(...),
    user_id: int = Depends(current_user_id),
):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    try:
        interval = f"{start_date}T00:00:00Z--{end_date}T23:59:59Z"
        resp = sp.sales.get_order_metrics(
            interval=interval, granularity="Day", granularity_time_zone="UTC"
        )
        return JSONResponse({"status": "success", "data": resp.payload})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=502)


class ProfitRequest(BaseModel):
    asin: str
    cost: float
    price: float | None = None
    customer_shipping: float = 0.0
    shipping_cost: float = 0.0
    other_costs: float = 0.0
    currency_code: str | None = None


@router.post("/fba-profit-calculator")
async def fba_profit_calculator(data: ProfitRequest, user_id: int = Depends(current_user_id)):
    return await _profit_response(data, user_id, fulfillment="FBA")


@router.post("/fbm-profit-calculator")
async def fbm_profit_calculator(data: ProfitRequest, user_id: int = Depends(current_user_id)):
    """Calculate one FBM product manually; there is intentionally no bulk FBM route."""
    return await _profit_response(data, user_id, fulfillment="FBM")


async def _profit_response(data: ProfitRequest, user_id: int, *, fulfillment: str):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    calculator = AmazonProfitCalculator(sp)
    try:
        result = await run_in_threadpool(
            calculator.calculate,
            data.asin,
            data.cost,
            fulfillment=fulfillment,
            price=data.price,
            customer_shipping=data.customer_shipping,
            shipping_cost=data.shipping_cost,
            other_costs=data.other_costs,
            currency_code=data.currency_code,
        )
        return JSONResponse(result)
    except ValueError as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=400)
    except Exception as exc:  # SP-API/network failure
        return JSONResponse(
            {"status": "error", "message": f"Amazon profit calculation failed: {exc}"},
            status_code=502,
        )


@router.post("/revcalall")
async def revcalall(user_id: int = Depends(current_user_id)):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    with get_db().session() as session:
        store = AppStateStore(session)
        scraped_blob = store.get(user_id, AppStateStore.SCRAPED) or {}
        checked_blob = store.get(user_id, AppStateStore.CHECKED) or {}
    scraped = _decode_scraped(scraped_blob.get("raw_string", ""))
    if not scraped:
        return JSONResponse(
            {"status": "error", "message": "No scraped products are available."},
            status_code=400,
        )

    try:
        outcome = await run_in_threadpool(
            _bulk_fba,
            sp,
            scraped,
            checked_blob.get("results") or {},
        )
    except Exception as exc:
        return JSONResponse(
            {"status": "error", "message": f"Bulk FBA calculation failed: {exc}"},
            status_code=502,
        )
    with get_db().session() as session:
        AppStateStore(session).set(user_id, AppStateStore.FBA_RESULTS, outcome)
    return JSONResponse({"status": "success", **outcome})


def _bulk_fba(sp: Any, products: list[Any], checked: dict[str, Any]) -> dict[str, Any]:
    calculator = AmazonProfitCalculator(sp)
    results: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in products:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("search_key") or item.get("unit") or "").strip()
        asin = _asin_for(item, source_key, checked)
        cost = _cost_for(item)
        if not asin:
            skipped.append({"search_key": source_key, "reason": "No matched ASIN"})
            continue
        if cost is None:
            skipped.append({"search_key": source_key, "asin": asin, "reason": "No cost price"})
            continue
        try:
            result = calculator.calculate(asin, cost, fulfillment="FBA")
            result["search_key"] = source_key
            results.append(result)
        except Exception as exc:
            skipped.append({"search_key": source_key, "asin": asin, "reason": str(exc)})
    return {
        "data": results,
        "results": results,
        "skipped": skipped,
        "summary": {"total": len(products), "calculated": len(results), "skipped": len(skipped)},
    }


def _asin_for(item: dict[str, Any], source_key: str, checked: dict[str, Any]) -> str | None:
    direct = item.get("ASIN") or item.get("asin")
    candidates = item.get("amazon_data") or checked.get(source_key) or []
    if not direct and isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict):
            direct = first.get("productASIN") or first.get("asin")
    if not direct and re.fullmatch(r"[A-Z0-9]{10}", source_key, re.IGNORECASE):
        direct = source_key
    value = str(direct or "").strip().upper()
    return value if re.fullmatch(r"[A-Z0-9]{10}", value) else None


def _cost_for(item: dict[str, Any]) -> float | None:
    for key in ("Unit Price", "Our Price", "unit_price", "cost", "Cost"):
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
            if match:
                return float(match.group(0))
    return None


def _decode_scraped(raw_string: str) -> list[Any]:
    if not raw_string:
        return []
    try:
        data = json.loads(raw_string)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("data", [])
    return data if isinstance(data, list) else []
