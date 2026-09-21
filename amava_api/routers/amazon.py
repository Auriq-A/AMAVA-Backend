"""Amazon catalog matching and gated/ungated eligibility endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from amava_agent.check_un_gated import AmazonEligibilityChecker
from amava_agent.services import build_user_spapi

from ..deps import current_user_id, get_db
from ..store import AppStateStore

router = APIRouter(tags=["amazon"])


class CheckProductsRequest(BaseModel):
    values: list[str] | None = None
    search_keys: list[str] | None = None
    unit: str | None = None
    condition_type: str = "new_new"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_status(user_id: int, value: dict[str, Any]) -> None:
    with get_db().session() as session:
        AppStateStore(session).set(user_id, AppStateStore.AMAZON_STATUS, value)


@router.post("/check-products")
@router.post("/check-ungated", include_in_schema=False)
async def check_products(
    payload: CheckProductsRequest | None = None,
    user_id: int = Depends(current_user_id),
):
    """Resolve product keys to ASINs, check restrictions, and store results.

    Pass ``values`` (or ``search_keys``), or omit them to use the values last
    saved through POST /search-key. The compatibility alias /check-ungated
    executes the same operation.
    """
    payload = payload or CheckProductsRequest()
    values = payload.values or payload.search_keys
    unit = payload.unit
    if not values:
        with get_db().session() as session:
            stored = AppStateStore(session).get(user_id, AppStateStore.SEARCH_KEY) or {}
        values = stored.get("data") or []
        unit = unit or stored.get("unit")
    unit = unit or "search_key"
    values = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    if not values:
        return JSONResponse(
            {"status": "error", "message": "No product search keys were provided or stored."},
            status_code=400,
        )

    try:
        spapi = build_user_spapi(user_id)
        checker = AmazonEligibilityChecker(spapi)
    except ValueError as exc:
        message = str(exc)
        status_code = 503 if "no stored Amazon" in message else 400
        return JSONResponse({"status": "error", "message": message}, status_code=status_code)
    except Exception as exc:  # credential decryption/client construction
        return JSONResponse(
            {"status": "error", "message": f"Amazon SP-API is unavailable: {exc}"},
            status_code=503,
        )

    started_at = _now()
    _set_status(user_id, {
        "status": "running", "total": len(values), "processed": 0,
        "started_at": started_at, "updated_at": started_at,
    })

    def progress(processed: int, total: int, _item: dict[str, Any] | None) -> None:
        if processed == total or processed % 5 == 0:
            _set_status(user_id, {
                "status": "running", "total": total, "processed": processed,
                "started_at": started_at, "updated_at": _now(),
            })

    try:
        outcome = await run_in_threadpool(
            checker.check_many,
            values,
            unit=unit,
            condition_type=payload.condition_type,
            progress=progress,
        )
    except Exception as exc:
        _set_status(user_id, {
            "status": "error", "total": len(values), "processed": 0,
            "message": str(exc), "started_at": started_at, "updated_at": _now(),
        })
        return JSONResponse(
            {"status": "error", "message": f"Amazon eligibility check failed: {exc}"},
            status_code=502,
        )

    completed_at = _now()
    checked_blob = {
        "results": outcome["results"], "skipped": outcome["skipped"],
        "summary": outcome["summary"], "unit": unit, "timestamp": completed_at,
    }
    with get_db().session() as session:
        store = AppStateStore(session)
        store.set(user_id, AppStateStore.CHECKED, checked_blob)
        store.set(user_id, AppStateStore.AMAZON_STATUS, {
            "status": "completed", "total": len(values), "processed": len(values),
            "summary": outcome["summary"], "started_at": started_at,
            "updated_at": completed_at,
        })
    return JSONResponse({"status": "success", **checked_blob})


@router.get("/amazon-checking-status")
async def amazon_checking_status(user_id: int = Depends(current_user_id)):
    with get_db().session() as session:
        value = AppStateStore(session).get(user_id, AppStateStore.AMAZON_STATUS)
    return JSONResponse({
        "status": "success",
        "amazon_checking_status": value or {"status": "idle", "processed": 0, "total": 0},
    })


@router.post("/amazon-checking-status")
async def set_amazon_checking_status(
    request: Request,
    user_id: int = Depends(current_user_id),
):
    """Compatibility setter for the legacy frontend's progress indicator."""
    value = await request.json()
    if not isinstance(value, dict):
        return JSONResponse({"status": "error", "message": "Body must be an object."}, 400)
    value["updated_at"] = _now()
    _set_status(user_id, value)
    return JSONResponse({"status": "success", "amazon_checking_status": value})
