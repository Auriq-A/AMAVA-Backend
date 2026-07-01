"""Amazon SP-API endpoints — per-user, credentials from the encrypted vault.

Every endpoint resolves the acting user and builds their SP-API client via
``amava_agent.services.build_user_spapi`` (creds decrypted from the vault). If
the user hasn't connected Amazon yet, we return a clean 503 instead of doing
anything — so NOTHING here uses live SP-API until a user explicitly stores
credentials (honoring "SP-API later"). No keys are ever hardcoded.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from amava_agent.services import build_user_spapi

from ..deps import current_user_id

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


@router.post("/fba-profit-calculator")
async def fba_profit_calculator(data: ProfitRequest, user_id: int = Depends(current_user_id)):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    # The Fees Estimate API isn't in sp_api_amazon yet; pricing/offers are. Net
    # profit needs fees, so this is the one SP-API feature still to come.
    return JSONResponse(
        {"status": "error", "message": "FBA profit calc is coming soon (Fees API pending)."},
        status_code=501,
    )


@router.post("/revcalall")
async def revcalall(user_id: int = Depends(current_user_id)):
    sp = _client(user_id)
    if sp is None:
        return _NOT_CONNECTED
    return JSONResponse(
        {"status": "error", "message": "Bulk revenue calc is coming soon (Fees API pending)."},
        status_code=501,
    )
