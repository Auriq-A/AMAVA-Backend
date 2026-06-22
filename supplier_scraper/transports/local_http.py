"""Local httpx transport (no Bright Data, no proxy).

Falls back from WebUnlockerTransport when BRIGHTDATA_USE=false.

Good for: development, testing, public sites that don't block plain HTTP.
Not good for: sites that return 403 / CAPTCHA for bot-looking requests —
use WebUnlockerTransport for those (needs Bright Data credentials).
"""
from __future__ import annotations

import httpx

from ..exceptions import TransportError
from .base import FetchResult, Transport

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class LocalHttpTransport(Transport):
    """Direct httpx GET — no proxy, no Bright Data."""

    name = "local_http"

    def __init__(self, _config=None, *, timeout: float = 30.0) -> None:
        # _config accepted but ignored — keeps the constructor signature
        # compatible with WebUnlockerTransport so the scraper can swap them.
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        )

    async def fetch(self, url: str, *, wait_for: str | None = None) -> FetchResult:
        # wait_for is ignored — no JS execution on a plain HTTP request.
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise TransportError(f"HTTP request failed: {exc}", url=url) from exc
        if resp.status_code >= 400:
            raise TransportError(
                f"HTTP {resp.status_code} from {url}", url=url, status_code=resp.status_code
            )
        return FetchResult(url=str(resp.url), html=resp.text, status_code=resp.status_code)

    async def aclose(self) -> None:
        await self._client.aclose()
