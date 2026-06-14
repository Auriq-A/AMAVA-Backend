"""Login With Amazon (LWA) token management.

The seller's refresh token is exchanged for a short-lived access token, which
is sent on every SP-API call as the ``x-amz-access-token`` header. Tokens are
cached and refreshed automatically a little before they expire, and access is
guarded by a lock so concurrent callers don't stampede the token endpoint.

Two token flavors:
  * normal access token (default) - from the seller's refresh token.
  * grantless token - client-credentials grant for a specific scope, used by a
    handful of operations (e.g. Notifications) that don't act on seller data.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests

from .config import Credentials
from .exceptions import SPAPIAuthError
from .marketplaces import LWA_TOKEN_URL

# Refresh this many seconds before the real expiry to avoid using a token that
# dies mid-flight.
_EXPIRY_SKEW = 60.0


@dataclass
class _CachedToken:
    value: str
    expires_at: float  # epoch seconds

    @property
    def is_valid(self) -> bool:
        return bool(self.value) and time.time() < (self.expires_at - _EXPIRY_SKEW)


class AccessTokenManager:
    """Fetches and caches LWA access tokens."""

    def __init__(
        self,
        credentials: Credentials,
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._creds = credentials
        self._session = session or requests.Session()
        self._timeout = timeout
        self._lock = threading.Lock()
        self._normal: _CachedToken | None = None
        # Grantless tokens are cached per scope.
        self._grantless: dict[str, _CachedToken] = {}

    def get_access_token(self) -> str:
        """Return a valid seller access token, refreshing if necessary."""
        with self._lock:
            if self._normal and self._normal.is_valid:
                return self._normal.value
            self._normal = self._request_token(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": self._creds.refresh_token,
                }
            )
            return self._normal.value

    def get_grantless_token(self, scope: str) -> str:
        """Return a valid grantless token for the given scope."""
        with self._lock:
            cached = self._grantless.get(scope)
            if cached and cached.is_valid:
                return cached.value
            token = self._request_token(
                {"grant_type": "client_credentials", "scope": scope}
            )
            self._grantless[scope] = token
            return token.value

    def invalidate(self) -> None:
        """Drop all cached tokens (e.g. after a 401) to force a refresh."""
        with self._lock:
            self._normal = None
            self._grantless.clear()

    # -- internal ---------------------------------------------------------
    def _request_token(self, payload: dict[str, str]) -> _CachedToken:
        body = {
            **payload,
            "client_id": self._creds.lwa_client_id,
            "client_secret": self._creds.lwa_client_secret,
        }
        try:
            resp = self._session.post(
                LWA_TOKEN_URL,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:  # network failure
            raise SPAPIAuthError(f"LWA token request failed: {exc}") from exc

        data: dict = {}
        try:
            data = resp.json()
        except ValueError:
            pass

        if resp.status_code != 200 or "access_token" not in data:
            desc = data.get("error_description") or data.get("error") or resp.text
            raise SPAPIAuthError(
                f"LWA token exchange rejected: {desc}",
                status_code=resp.status_code,
            )

        expires_in = float(data.get("expires_in", 3600))
        return _CachedToken(
            value=data["access_token"],
            expires_at=time.time() + expires_in,
        )
