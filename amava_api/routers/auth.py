"""Account auth — register / login / me.

Backed by amava_db.UserService (PBKDF2 password hashing + API keys). Login and
register both return an API key the frontend stores and sends as ``X-API-Key``
on every request; deps.current_user_id then resolves that to the real user, so
all data (scrapes, credentials, sessions) is scoped per account.
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from amava_db import UserService

from ..deps import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Creds(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(c: Creds):
    email = c.email.strip().lower()
    if not email or not c.password:
        return JSONResponse({"status": "error", "message": "Email and password are required."}, 400)
    if len(c.password) < 6:
        return JSONResponse({"status": "error", "message": "Password must be at least 6 characters."}, 400)
    with get_db().session() as s:
        users = UserService(s)
        if users.get_by_email(email):
            return JSONResponse({"status": "error", "message": "An account with this email already exists."}, 409)
        user = users.create_user(email, c.password)
        _, raw_key = users.issue_api_key(user.id, name="web")
        return JSONResponse({"status": "success", "email": user.email, "api_key": raw_key})


@router.post("/login")
async def login(c: Creds):
    email = c.email.strip().lower()
    with get_db().session() as s:
        users = UserService(s)
        user = users.authenticate(email, c.password)
        if not user:
            return JSONResponse({"status": "error", "message": "Invalid email or password."}, 401)
        _, raw_key = users.issue_api_key(user.id, name="web")
        return JSONResponse({"status": "success", "email": user.email, "api_key": raw_key})


@router.get("/me")
async def me(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not x_api_key:
        return JSONResponse({"status": "error", "authenticated": False}, 401)
    with get_db().session() as s:
        user = UserService(s).verify_api_key(x_api_key)
    if not user:
        return JSONResponse({"status": "error", "authenticated": False}, 401)
    return JSONResponse({"status": "success", "authenticated": True, "email": user.email})
