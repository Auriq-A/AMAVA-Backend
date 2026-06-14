"""Resolve the current tenant (user) from the ADK tool context.

Contract: the SaaS API layer authenticates the user, then opens the ADK session
with the AMAVA user id as the session user_id (and/or puts it in session state
as "user_id"). Tools call current_user_id() to scope all data access.
"""
from __future__ import annotations

from typing import Any


def current_user_id(tool_context: Any) -> int | None:
    if tool_context is None:
        return None

    raw = None
    # Preferred: explicit session state set by the API layer.
    try:
        raw = tool_context.state.get("user_id")
    except Exception:  # noqa: BLE001 - state may be missing/odd in some contexts
        raw = None

    # Fallback: the ADK session's user_id (set when the session was created).
    if raw is None:
        ic = getattr(tool_context, "_invocation_context", None)
        session = getattr(ic, "session", None) if ic is not None else None
        raw = getattr(session, "user_id", None) if session is not None else None

    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
