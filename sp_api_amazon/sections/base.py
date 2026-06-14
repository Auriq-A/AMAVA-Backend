"""Base class for every API section.

A section is a thin object that knows its URL prefix and turns friendly Python
methods into ``client.request(...)`` calls. Keeping the shared plumbing here
means each concrete section (Orders, Listings, ...) stays short and readable -
to add an operation you write one small method following the same pattern.
"""
from __future__ import annotations

from typing import Any

from ..client import SPAPIClient, SPAPIResponse


class BaseSection:
    #: URL prefix common to every operation in this section,
    #: e.g. "/orders/v0". Concrete sections override this.
    path_prefix: str = ""

    def __init__(self, client: SPAPIClient) -> None:
        self._client = client

    @property
    def marketplace_id(self) -> str:
        return self._client.config.marketplace.marketplace_id

    def _full_path(self, suffix: str = "") -> str:
        return f"{self.path_prefix}{suffix}"

    def _get(
        self,
        suffix: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        restricted_resources: list[dict[str, Any]] | None = None,
    ) -> SPAPIResponse:
        return self._client.request(
            "GET",
            self._full_path(suffix),
            operation=operation,
            params=params,
            restricted_resources=restricted_resources,
        )

    def _post(
        self,
        suffix: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        grantless_scope: str | None = None,
    ) -> SPAPIResponse:
        return self._client.request(
            "POST",
            self._full_path(suffix),
            operation=operation,
            params=params,
            json_body=json_body,
            grantless_scope=grantless_scope,
        )

    def _put(
        self,
        suffix: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> SPAPIResponse:
        return self._client.request(
            "PUT",
            self._full_path(suffix),
            operation=operation,
            params=params,
            json_body=json_body,
        )

    def _patch(
        self,
        suffix: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> SPAPIResponse:
        return self._client.request(
            "PATCH",
            self._full_path(suffix),
            operation=operation,
            params=params,
            json_body=json_body,
        )

    def _delete(
        self,
        suffix: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> SPAPIResponse:
        return self._client.request(
            "DELETE",
            self._full_path(suffix),
            operation=operation,
            params=params,
        )

    def _default_marketplace_ids(
        self, marketplace_ids: list[str] | None
    ) -> list[str]:
        """Fall back to the configured marketplace when the caller omits the
        marketplaceIds argument (the common case)."""
        return marketplace_ids or [self.marketplace_id]
