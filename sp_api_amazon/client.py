"""The core request engine shared by every API section.

Responsibilities (everything that is the same for all operations):
  * acquire an access token (normal / grantless / Restricted Data Token)
  * enforce per-operation rate limits
  * issue the HTTP request (optionally SigV4-signed)
  * retry throttling/server/expired-token failures with exponential backoff
  * parse the response into an SPAPIResponse, or raise a typed SPAPIError

Section classes (Orders, Listings, ...) only build paths/params/bodies and
hand them to ``SPAPIClient.request``.
"""
from __future__ import annotations

import json as _json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from .auth import AccessTokenManager
from .config import SPAPIConfig
from .exceptions import SPAPIError, error_for_status
from .rate_limit import RateLimiter
from . import signers

# Path of the Tokens API operation used to mint Restricted Data Tokens.
_RDT_PATH = "/tokens/2021-03-01/restrictedDataToken"


@dataclass
class SPAPIResponse:
    """A thin, friendly wrapper around a successful SP-API response."""

    status_code: int
    raw: Any                                   # parsed JSON (dict/list) or None
    headers: dict[str, str] = field(default_factory=dict)
    request_id: str | None = None

    @property
    def payload(self) -> Any:
        """Most SP-APIs wrap results in {"payload": ...}; newer ones return the
        object directly. This returns whichever applies."""
        if isinstance(self.raw, dict) and "payload" in self.raw:
            return self.raw["payload"]
        return self.raw

    @property
    def errors(self) -> list[dict[str, Any]]:
        if isinstance(self.raw, dict):
            return self.raw.get("errors", []) or []
        return []

    @property
    def next_token(self) -> str | None:
        """Pagination token, wherever Amazon happened to put it."""
        if not isinstance(self.raw, dict):
            return None
        if self.raw.get("nextToken"):
            return self.raw["nextToken"]
        payload = self.payload
        if isinstance(payload, dict):
            return payload.get("NextToken") or payload.get("nextToken") or (
                payload.get("pagination", {}) or {}
            ).get("nextToken")
        return None

    def get(self, key: str, default: Any = None) -> Any:
        payload = self.payload
        if isinstance(payload, dict):
            return payload.get(key, default)
        return default


@dataclass
class _CachedRDT:
    value: str
    expires_at: float


class SPAPIClient:
    def __init__(self, config: SPAPIConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.auth = AccessTokenManager(
            config.credentials, session=self.session, timeout=config.timeout
        )
        self.rate_limiter = RateLimiter()
        self._rdt_cache: dict[str, _CachedRDT] = {}

    # -- public API -------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        restricted_resources: list[dict[str, Any]] | None = None,
        grantless_scope: str | None = None,
    ) -> SPAPIResponse:
        """Execute one SP-API call. ``operation`` is the camelCase operation
        name (used for rate limiting and RDT scoping)."""
        url = self.config.endpoint + path
        body_bytes = (
            _json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            if json_body is not None
            else b""
        )
        query = _clean_params(params)

        attempt = 0
        while True:
            attempt += 1
            # Respect this operation's quota before every attempt.
            self.rate_limiter.acquire(operation)

            token = self._token_for(
                restricted_resources=restricted_resources,
                grantless_scope=grantless_scope,
            )
            req_headers = self._build_headers(token, headers, has_body=bool(body_bytes))

            if self.config.use_sigv4 and self.config.credentials.has_aws_keys:
                req_headers.update(
                    signers.sign_request(
                        method=method,
                        url=_full_url(url, query),
                        region=self.config.region.aws_region,
                        access_key=self.config.credentials.aws_access_key_id,  # type: ignore[arg-type]
                        secret_key=self.config.credentials.aws_secret_access_key,  # type: ignore[arg-type]
                        headers=req_headers,
                        body=body_bytes,
                    )
                )

            try:
                resp = self.session.request(
                    method.upper(),
                    url,
                    params=query or None,
                    data=body_bytes or None,
                    headers=req_headers,
                    timeout=self.config.timeout,
                )
            except requests.RequestException as exc:
                if attempt <= self.config.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise SPAPIError(f"Request to {path} failed: {exc}") from exc

            # Feed real quota back into the limiter for next time.
            self.rate_limiter.update_from_header(
                operation, resp.headers.get("x-amzn-RateLimit-Limit")
            )

            if resp.status_code < 300:
                return _parse_success(resp)

            # Decide whether this failure is worth another attempt.
            if self._should_retry(resp.status_code) and attempt <= self.config.max_retries:
                if resp.status_code in (401, 403):
                    # Stale token: drop caches so the next loop re-mints.
                    self.auth.invalidate()
                    self._rdt_cache.clear()
                self._sleep_backoff(attempt, resp)
                continue

            raise _parse_error(resp)

    # -- token handling ---------------------------------------------------
    def _token_for(
        self,
        *,
        restricted_resources: list[dict[str, Any]] | None,
        grantless_scope: str | None,
    ) -> str:
        if grantless_scope:
            return self.auth.get_grantless_token(grantless_scope)
        if restricted_resources:
            return self._get_rdt(restricted_resources)
        return self.auth.get_access_token()

    def _get_rdt(self, restricted_resources: list[dict[str, Any]]) -> str:
        """Mint (and cache) a Restricted Data Token for the given resources."""
        key = _json.dumps(restricted_resources, sort_keys=True)
        cached = self._rdt_cache.get(key)
        if cached and time.time() < cached.expires_at - 60:
            return cached.value

        self.rate_limiter.acquire("createRestrictedDataToken")
        token = self.auth.get_access_token()
        resp = self.session.post(
            self.config.endpoint + _RDT_PATH,
            data=_json.dumps({"restrictedResources": restricted_resources}),
            headers=self._build_headers(token, None, has_body=True),
            timeout=self.config.timeout,
        )
        if resp.status_code >= 300:
            raise _parse_error(resp)
        data = resp.json()
        rdt = data["restrictedDataToken"]
        self._rdt_cache[key] = _CachedRDT(
            value=rdt, expires_at=time.time() + float(data.get("expiresIn", 3600))
        )
        return rdt

    # -- helpers ----------------------------------------------------------
    def _build_headers(
        self, token: str, extra: dict[str, str] | None, *, has_body: bool
    ) -> dict[str, str]:
        headers = {
            "x-amz-access-token": token,
            "user-agent": self.config.user_agent,
            "accept": "application/json",
            **self.config.default_headers,
        }
        if has_body:
            headers["content-type"] = "application/json"
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        return status_code in (401, 403, 429) or 500 <= status_code < 600

    def _sleep_backoff(self, attempt: int, resp: requests.Response | None = None) -> None:
        # Honor Retry-After if Amazon sent one.
        if resp is not None:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(min(float(retry_after), self.config.backoff_max))
                    return
                except ValueError:
                    pass
        delay = min(
            self.config.backoff_base * (2 ** (attempt - 1)), self.config.backoff_max
        )
        # Full jitter to avoid synchronized retries across callers.
        time.sleep(random.uniform(0, delay))


# -- module-level helpers -------------------------------------------------
def _clean_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Drop None values and join list params into comma-separated strings, the
    form SP-API expects for repeated query parameters."""
    if not params:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            cleaned[key] = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        else:
            cleaned[key] = value
    return cleaned


def _full_url(url: str, query: dict[str, Any]) -> str:
    if not query:
        return url
    from urllib.parse import urlencode

    return f"{url}?{urlencode(query)}"


def _parse_json(resp: requests.Response) -> Any:
    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _parse_success(resp: requests.Response) -> SPAPIResponse:
    return SPAPIResponse(
        status_code=resp.status_code,
        raw=_parse_json(resp),
        headers=dict(resp.headers),
        request_id=resp.headers.get("x-amzn-RequestId"),
    )


def _parse_error(resp: requests.Response) -> SPAPIError:
    data = _parse_json(resp)
    errors = data.get("errors") if isinstance(data, dict) else None
    if errors:
        message = "; ".join(
            e.get("message", "") for e in errors if isinstance(e, dict)
        ) or "SP-API request failed"
    else:
        message = (resp.text or "SP-API request failed")[:500]
    return error_for_status(
        resp.status_code,
        message,
        errors=errors,
        headers=dict(resp.headers),
        request_id=resp.headers.get("x-amzn-RequestId"),
    )
