"""Transport interface.

A transport's only job is: given a URL (and an optional element to wait for),
return the page's rendered HTML. Two implementations:
  * WebUnlockerTransport   - stateless, cheap, public pages.
  * ScrapingBrowserSession - stateful browser (login, JS, pagination clicks).

The orchestrator picks one per supplier; extraction is transport-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FetchResult:
    url: str
    html: str
    status_code: int | None = None


class Transport:
    """Abstract transport. Async because the browser backend must be."""

    name: str = "transport"

    async def fetch(self, url: str, *, wait_for: str | None = None) -> FetchResult:
        raise NotImplementedError

    async def aclose(self) -> None:  # pragma: no cover - default no-op
        return None

    async def __aenter__(self) -> "Transport":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
