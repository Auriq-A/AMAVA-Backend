"""Exception hierarchy for the SP-API client.

Every failure surfaces as an SPAPIError (or subclass) so callers can catch one
base type. HTTP-status-specific subclasses make common handling (throttling,
auth) easy without parsing strings.
"""
from __future__ import annotations

from typing import Any


class SPAPIError(Exception):
    """Base class for all SP-API errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.errors = errors or []
        self.headers = headers or {}
        self.request_id = request_id

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        base = self.message
        if self.status_code is not None:
            base = f"[{self.status_code}] {base}"
        if self.request_id:
            base = f"{base} (request-id: {self.request_id})"
        return base


class SPAPIConfigError(SPAPIError):
    """Raised when credentials/config are missing or invalid (no HTTP call)."""


class SPAPIAuthError(SPAPIError):
    """401/403 - bad or expired token, or operation not authorized."""


class SPAPIThrottledError(SPAPIError):
    """429 - request rate exceeded the operation's quota."""


class SPAPINotFoundError(SPAPIError):
    """404 - the requested resource does not exist."""


class SPAPIValidationError(SPAPIError):
    """400 - the request was malformed or failed Amazon's validation."""


class SPAPIServerError(SPAPIError):
    """5xx - a transient/server-side failure on Amazon's end."""


def error_for_status(
    status_code: int,
    message: str,
    *,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    request_id: str | None = None,
) -> SPAPIError:
    """Map an HTTP status code to the most specific SPAPIError subclass."""
    kwargs = dict(
        status_code=status_code,
        errors=errors,
        headers=headers,
        request_id=request_id,
    )
    if status_code in (401, 403):
        return SPAPIAuthError(message, **kwargs)
    if status_code == 404:
        return SPAPINotFoundError(message, **kwargs)
    if status_code == 429:
        return SPAPIThrottledError(message, **kwargs)
    if status_code == 400:
        return SPAPIValidationError(message, **kwargs)
    if 500 <= status_code < 600:
        return SPAPIServerError(message, **kwargs)
    return SPAPIError(message, **kwargs)
