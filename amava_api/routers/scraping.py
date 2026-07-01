"""Scraping / ungating data flow — per-user, DB-backed.

Mirrors the old server's contract exactly (same paths, same response shapes) so
the existing frontend works unchanged, but every blob is scoped to the acting
user via AppStateStore instead of global in-memory state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..deps import current_user_id, get_db
from ..store import AppStateStore

router = APIRouter(tags=["scraping"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- scraped data -----------------------------------------------------------
@router.post("/api/scraped_dataresults")
async def receive_scraped_data(request: Request, user_id: int = Depends(current_user_id)):
    raw_str = (await request.body()).decode("utf-8")
    try:
        parsed = json.loads(raw_str)
    except json.JSONDecodeError as exc:
        return JSONResponse({"status": "error", "error": f"Invalid JSON: {exc}"}, 400)

    count = len(parsed.get("data", parsed)) if isinstance(parsed, (list, dict)) else 0
    with get_db().session() as s:
        AppStateStore(s).set(user_id, AppStateStore.SCRAPED, {
            "raw_string": raw_str, "items_count": count, "saved_at": _now(),
        })
    return JSONResponse({"status": "success", "message": "Data stored", "items_count": count})


@router.get("/api/get_scraped_data")
async def get_scraped_data(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        blob = AppStateStore(s).get(user_id, AppStateStore.SCRAPED) or {}
    return JSONResponse({
        "status": "success",
        "raw_string": blob.get("raw_string", ""),
        "items_count": blob.get("items_count", 0),
    })


# -- search keys ------------------------------------------------------------
@router.post("/search-key")
async def save_search_key(request: Request, user_id: int = Depends(current_user_id)):
    data = await request.json()
    if isinstance(data, dict) and "values" in data:
        values, unit = data["values"], data.get("unit", "search_key")
    elif isinstance(data, list):
        values, unit = data, "search_key"
    else:
        return JSONResponse(
            {"status": "error", "error": "Body must be a list or {values, unit}."}, 400
        )
    if not isinstance(values, list):
        return JSONResponse({"status": "error", "error": "'values' must be a list."}, 400)

    with get_db().session() as s:
        AppStateStore(s).set(user_id, AppStateStore.SEARCH_KEY, {
            "data": values, "unit": unit, "saved_at": _now(),
        })
    return JSONResponse({"status": "success", "message": "Search key data saved.", "count": len(values)})


@router.get("/search-key")
async def get_search_key(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        blob = AppStateStore(s).get(user_id, AppStateStore.SEARCH_KEY) or {}
    return JSONResponse({
        "status": "success",
        "data": blob.get("data", []),
        "unit": blob.get("unit", "search_key"),
        "saved_at": blob.get("saved_at"),
    })


# -- checked (Amazon match) data -------------------------------------------
@router.post("/checkeddata")
async def receive_checked_data(request: Request, user_id: int = Depends(current_user_id)):
    data = await request.json()
    with get_db().session() as s:
        AppStateStore(s).set(user_id, AppStateStore.CHECKED, {
            "results": data.get("results", {}),
            "skipped": data.get("skipped", []),
            "unit": data.get("unit", "search_key"),
            "timestamp": _now(),
        })
    return JSONResponse({"status": "success", "message": "Checked data stored."})


@router.get("/checkeddata")
async def get_checked_data(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        blob = AppStateStore(s).get(user_id, AppStateStore.CHECKED)
    if not blob or not blob.get("results"):
        return JSONResponse({"status": "empty", "message": "No checked data available."}, 404)
    return JSONResponse({"status": "success", "checked_data": blob})


@router.delete("/remove-checkeddata")
async def remove_checked_data(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        AppStateStore(s).delete(user_id, AppStateStore.CHECKED)
    return JSONResponse({"status": "success", "message": "All checked data removed."})


# -- merged view for the ungating excel table ------------------------------
@router.get("/exceldata")
async def get_merged_excel_data(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        store = AppStateStore(s)
        scraped_blob = store.get(user_id, AppStateStore.SCRAPED) or {}
        checked_blob = store.get(user_id, AppStateStore.CHECKED) or {}

    scraped = _decode_scraped(scraped_blob.get("raw_string", ""))
    amazon = checked_blob.get("results", {}) or {}

    merged = []
    for item in scraped:
        if not isinstance(item, dict):
            continue
        key = item.get("search_key") or item.get("unit")
        out = dict(item)
        out["amazon_data"] = amazon.get(key, [])
        merged.append(out)

    return JSONResponse({
        "status": "success",
        "merged_data": merged,
        "scraped_count": len(scraped),
        "merged_count": len(merged),
    })


def _decode_scraped(raw_string: str) -> list:
    if not raw_string:
        return []
    try:
        data = json.loads(raw_string)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    return data if isinstance(data, list) else []
