"""Optional AWS Signature Version 4 signing.

Modern SP-API authenticates with the LWA access token alone and does **not**
require SigV4. This module exists only for the rare case where signing is
explicitly enabled (config.use_sigv4=True) - e.g. talking to an older
integration path. It is self-contained and off by default.

The algorithm is the standard AWS SigV4 flow:
  1. Canonical request -> hash
  2. String to sign (scope + canonical-request hash)
  3. Signing key (derived from secret + date/region/service)
  4. Signature -> Authorization header
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
from urllib.parse import quote, urlparse

_SERVICE = "execute-api"
_ALGORITHM = "AWS4-HMAC-SHA256"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    k_date = _hmac(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, _SERVICE)
    return _hmac(k_service, "aws4_request")


def sign_request(
    *,
    method: str,
    url: str,
    region: str,
    access_key: str,
    secret_key: str,
    headers: dict[str, str],
    body: bytes = b"",
    session_token: str | None = None,
) -> dict[str, str]:
    """Return the headers needed to authorize this request with SigV4.

    The returned dict (Authorization, X-Amz-Date, and X-Amz-Security-Token if a
    session token is supplied) should be merged into the outgoing headers.
    """
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = quote(parsed.path or "/", safe="/-_.~")

    # Canonical query string: sorted, individually encoded key=value pairs.
    canonical_query = ""
    if parsed.query:
        pairs = []
        for part in parsed.query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
            else:
                k, v = part, ""
            pairs.append((quote(k, safe="-_.~"), quote(v, safe="-_.~")))
        pairs.sort()
        canonical_query = "&".join(f"{k}={v}" for k, v in pairs)

    now = _dt.datetime.now(_dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    payload_hash = _sha256_hex(body)

    signed_headers_map = {
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }
    if session_token:
        signed_headers_map["x-amz-security-token"] = session_token

    sorted_header_keys = sorted(signed_headers_map)
    canonical_headers = "".join(
        f"{k}:{signed_headers_map[k].strip()}\n" for k in sorted_header_keys
    )
    signed_headers = ";".join(sorted_header_keys)

    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    credential_scope = f"{date_stamp}/{region}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            _ALGORITHM,
            amz_date,
            credential_scope,
            _sha256_hex(canonical_request.encode("utf-8")),
        ]
    )

    signature = hmac.new(
        _signing_key(secret_key, date_stamp, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"{_ALGORITHM} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    out = {
        "Authorization": authorization,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
    }
    if session_token:
        out["X-Amz-Security-Token"] = session_token
    return out
