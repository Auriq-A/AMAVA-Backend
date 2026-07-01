"""Shared dependencies: DB/box singletons and current-user resolution.

Reuses amava_agent's process-wide singletons so the API and the agent share one
database + encryption box.

Auth is intentionally a single seam (``current_user_id``). Phase 1 resolves a
local dev user; swapping in real auth (API key / JWT) later means changing only
this function.
"""
from __future__ import annotations

import secrets

from fastapi import Header

from amava_agent.runtime import get_box, get_db  # shared singletons
from amava_db import UserService

from .config import DEV_USER_EMAIL

__all__ = ["get_db", "get_box", "current_user_id"]


def current_user_id(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> int:
    """Resolve the acting user.

    If an ``X-API-Key`` header is present and valid, use that user (real
    multi-tenant path). Otherwise fall back to a local dev user, created on
    first use — so the existing single-user frontend keeps working today.
    """
    db = get_db()
    with db.session() as s:
        users = UserService(s)
        if x_api_key:
            user = users.verify_api_key(x_api_key)
            if user is not None:
                return user.id
        user = users.get_by_email(DEV_USER_EMAIL)
        if user is None:
            user = users.create_user(DEV_USER_EMAIL, secrets.token_urlsafe(24))
        return user.id
