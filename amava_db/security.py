"""Password hashing and API-key handling (stdlib only - no bcrypt dependency).

Passwords use PBKDF2-HMAC-SHA256 with a per-password random salt, stored in a
self-describing string. API keys are random tokens; only their SHA-256 hash is
stored, and the raw key is shown to the user exactly once.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

_PBKDF2_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iter_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# -- API keys -------------------------------------------------------------
_KEY_PREFIX = "amava_sk_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, key_hash). Store prefix + hash; show raw once."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    prefix = raw[: len(_KEY_PREFIX) + 6]
    return raw, prefix, hash_api_key(raw)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
