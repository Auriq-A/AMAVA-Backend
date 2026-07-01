"""Agent proxy: forward /run and ADK session calls to the agent api_server.

The frontend talks to this backend; this backend forwards agent traffic to the
ADK api_server (``adk api_server`` running the amava_agent). Configure the
target with AGENT_BACKEND.

Two things this proxy does beyond a dumb forward:
  * Auto-creates the ADK session (ADK 403s on /run if it's missing).
  * Injects the *resolved AMAVA user id* (from auth / the dev user) as the
    session user_id AND session state["user_id"], overriding whatever the
    frontend sent (it hardcodes 'us'). That's what lets the agent's tools
    scope data to the real tenant — see amava_agent.context.current_user_id.

Run the agent server separately, e.g.:
    adk api_server agents --allow_origins=http://localhost:5173 --port 1483
"""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..config import AGENT_BACKEND
from ..deps import current_user_id

router = APIRouter(tags=["agent"])

# Headers we must not forward verbatim. We drop the browser's Origin/Referer/
# Cookie too: this is a server-to-server call, and ADK's api_server returns 403
# for an Origin that isn't in its --allow_origins list. Stripping them makes the
# upstream see a same-origin request (no CORS rejection). httpx recomputes the
# transport headers (host/content-length/...).
_DROP_HEADERS = {
    "host", "content-length", "connection", "accept-encoding",
    "origin", "referer", "cookie",
}


def _forward_headers(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.headers.items() if k.lower() not in _DROP_HEADERS}


async def _send(method: str, path: str, *, body: bytes, headers: dict[str, str], timeout: float) -> Response:
    url = f"{AGENT_BACKEND}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, content=body, headers=headers)
    except httpx.ReadTimeout:
        return JSONResponse({"status": "error", "error": "Agent backend timed out"}, 504)
    except httpx.HTTPError as exc:
        return JSONResponse(
            {"status": "error", "error": f"Agent backend unreachable: {exc}"}, 502
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


async def _ensure_session(app_name: str, user_id: str, session_id: str, *, amava_user_id: int) -> None:
    """Idempotently ensure the ADK session exists, seeded with the tenant id.

    ADK doesn't auto-create sessions (it 403s on /run otherwise). We GET the
    session and POST-create it only on 404, putting the AMAVA user id into
    session state so the agent's tools resolve the tenant.
    """
    base = f"{AGENT_BACKEND}/apps/{app_name}/users/{user_id}/sessions/{session_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            existing = await client.get(base)
            if existing.status_code == 404:
                # The create endpoint takes the JSON body AS the session state.
                await client.post(base, json={"user_id": amava_user_id})
    except httpx.HTTPError:
        pass  # agent down / unreachable -> let /run surface the real error


@router.post("/run")
async def run(request: Request, user_id: int = Depends(current_user_id)) -> Response:
    raw = await request.body()
    try:
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict):
            data = {}
    except (ValueError, TypeError):
        data = {}

    uid = str(user_id)
    # Force the real tenant id (frontend hardcodes 'us').
    data["userId"] = uid
    app_name = data.get("appName") or data.get("app_name") or "AMAVAGENT"
    session_id = data.get("sessionId") or data.get("session_id")
    if session_id:
        await _ensure_session(app_name, uid, session_id, amava_user_id=user_id)

    body = json.dumps(data).encode("utf-8")
    return await _send("POST", "/run", body=body, headers=_forward_headers(request), timeout=120.0)


@router.post("/apps/{app_name}/users/{user_id_path}/sessions/{session_id}")
async def session(
    app_name: str,
    user_id_path: str,
    session_id: str,
    request: Request,
    user_id: int = Depends(current_user_id),
) -> Response:
    # Rewrite the path to the resolved tenant id and seed state["user_id"], so a
    # session created here (or by the frontend's fallback) is owned by the real
    # user regardless of the 'us' the frontend sends.
    uid = str(user_id)
    path = f"/apps/{app_name}/users/{uid}/sessions/{session_id}"
    body = json.dumps({"user_id": user_id}).encode("utf-8")
    return await _send("POST", path, body=body, headers=_forward_headers(request), timeout=30.0)
