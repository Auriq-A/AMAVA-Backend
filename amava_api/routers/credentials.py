"""Credential management — saves SP-API + supplier logins to the encrypted vault.

Per-user (resolved via current_user_id). Secrets are AES/Fernet-encrypted at
rest by CredentialVault and NEVER returned in GET responses — status endpoints
report only whether something is connected, plus non-secret fields.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from amava_db import Credential, CredentialVault

from ..deps import current_user_id, get_box, get_db

router = APIRouter(prefix="/api/credentials", tags=["credentials"])

# Frontend supplier ids -> canonical supplier names (vault labels / scraper).
_SUPPLIERS = ("avasam", "888lots", "frontier")


# -- Amazon SP-API ----------------------------------------------------------
class SpapiCreds(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    seller_id: str | None = None
    marketplace: str = "US"


@router.post("/spapi")
async def save_spapi(creds: SpapiCreds, user_id: int = Depends(current_user_id)):
    if not (creds.client_id.strip() and creds.client_secret.strip() and creds.refresh_token.strip()):
        return JSONResponse(
            {"status": "error", "message": "client_id, client_secret and refresh_token are required."},
            status_code=400,
        )
    with get_db().session() as s:
        CredentialVault(s, get_box()).set_spapi(
            user_id,
            lwa_client_id=creds.client_id.strip(),
            lwa_client_secret=creds.client_secret.strip(),
            refresh_token=creds.refresh_token.strip(),
            seller_id=(creds.seller_id or "").strip() or None,
            marketplace=creds.marketplace or "US",
        )
    return JSONResponse({"status": "success", "message": "Amazon SP-API credentials saved."})


@router.get("/spapi")
async def get_spapi_status(user_id: int = Depends(current_user_id)):
    with get_db().session() as s:
        c = CredentialVault(s, get_box()).get_spapi(user_id)
    connected = bool(c and c.get("refresh_token") and c.get("lwa_client_id"))
    return JSONResponse({
        "status": "success",
        "connected": connected,
        # Non-secret fields only, to prefill the form. Never return secrets.
        "seller_id": (c or {}).get("seller_id") if connected else None,
        "marketplace": (c or {}).get("marketplace", "US") if connected else "US",
    })


@router.delete("/spapi")
async def disconnect_spapi(user_id: int = Depends(current_user_id)):
    _delete_cred(user_id, CredentialVault.PROVIDER_SPAPI, "")
    return JSONResponse({"status": "success", "message": "Amazon SP-API disconnected."})


# -- supplier logins --------------------------------------------------------
class SupplierCreds(BaseModel):
    supplier: str
    username: str = ""
    password: str = ""


@router.post("/supplier")
async def save_supplier(creds: SupplierCreds, user_id: int = Depends(current_user_id)):
    name = creds.supplier.strip().lower()
    if not name:
        return JSONResponse({"status": "error", "message": "supplier is required."}, status_code=400)
    with get_db().session() as s:
        CredentialVault(s, get_box()).set_supplier_login(
            user_id, name,
            username=creds.username.strip(), password=creds.password.strip(),
        )
    return JSONResponse({"status": "success", "message": f"{name} login saved."})


@router.get("/suppliers")
async def list_supplier_status(user_id: int = Depends(current_user_id)):
    connected: dict[str, bool] = {}
    with get_db().session() as s:
        vault = CredentialVault(s, get_box())
        for name in _SUPPLIERS:
            login = vault.get_supplier_login(user_id, name)
            connected[name] = bool(login and (login.get("username") or login.get("password")))
    return JSONResponse({"status": "success", "connected": connected})


@router.delete("/supplier/{supplier}")
async def disconnect_supplier(supplier: str, user_id: int = Depends(current_user_id)):
    _delete_cred(user_id, CredentialVault.PROVIDER_SUPPLIER, supplier.strip().lower())
    return JSONResponse({"status": "success", "message": f"{supplier} disconnected."})


# -- helper -----------------------------------------------------------------
def _delete_cred(user_id: int, provider: str, label: str) -> None:
    with get_db().session() as s:
        row = s.scalar(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.provider == provider,
                Credential.label == label,
            )
        )
        if row:
            s.delete(row)
            s.flush()
