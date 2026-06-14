"""Web Unlocker transport (stateless, cheap).

Calls Bright Data's Unlocker API:
    POST https://api.brightdata.com/request
    Authorization: Bearer <API_TOKEN>
    {"zone": "<zone>", "url": "<url>", "format": "raw"}

Returns the unblocked page HTML. No login/session - use this for public,
static supplier catalogs. ``wait_for`` is accepted for interface parity but
ignored (the Unlocker renders server-side).
"""
from __future__ import annotations

import httpx

from ..config import BrightDataConfig
from ..exceptions import TransportError
from .base import FetchResult, Transport


class WebUnlockerTransport(Transport):
    name = "unlocker"

    def __init__(self, config: BrightDataConfig, *, timeout: float = 90.0) -> None:
        config.require_unlocker()
        self._config = config
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {config.api_token}",
                "Content-Type": "application/json",
            },
        )

    async def fetch(self, url: str, *, wait_for: str | None = None) -> FetchResult:
        payload = {
            "zone": self._config.unlocker_zone,
            "url": url,
            "format": "raw",
        }
        try:
            resp = await self._client.post(self._config.unlocker_endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise TransportError(f"Web Unlocker request failed: {exc}", url=url) from exc

        if resp.status_code >= 400:
            raise TransportError(
                f"Web Unlocker returned {resp.status_code}: {resp.text[:300]}",
                url=url,
                status_code=resp.status_code,
            )
        return FetchResult(url=url, html=resp.text, status_code=resp.status_code)

    async def aclose(self) -> None:
        await self._client.aclose()
