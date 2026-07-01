"""Progress screenshots — per-user latest-image storage."""
from __future__ import annotations

import base64
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import SCREENSHOT_DIR
from ..deps import current_user_id

router = APIRouter(tags=["screenshots"])


class Screenshot(BaseModel):
    image_data: str
    filename: str | None = None


def _latest_path(user_id: int) -> str:
    d = os.path.join(SCREENSHOT_DIR, str(user_id))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "latest_screenshot.png")


@router.post("/upload-screenshot")
async def upload_screenshot(data: Screenshot, user_id: int = Depends(current_user_id)):
    if not data.image_data.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=400, detail="Invalid image data format")
    try:
        _, encoded = data.image_data.split(",", 1)
        image_bytes = base64.b64decode(encoded)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Image decoding failed: {exc}") from exc

    path = _latest_path(user_id)
    with open(path, "wb") as f:
        f.write(image_bytes)
    return {"status": "success", "message": "Image saved"}


@router.get("/get-screenshot")
async def get_screenshot(user_id: int = Depends(current_user_id)):
    path = _latest_path(user_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No screenshot available")
    return FileResponse(path, media_type="image/png")
