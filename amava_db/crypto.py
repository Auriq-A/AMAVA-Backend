"""Secret encryption for the credential vault.

Each user's Amazon SP-API tokens and supplier passwords are encrypted at rest
with Fernet (AES-128-CBC + HMAC). The encryption key is resolved, in priority
order, from:
  1. AMAVA_SECRET_KEY env var (any string; derived to a Fernet key) - use this
     in production.
  2. a key file (instance/secret.key) - auto-generated for local dev.

Rotating the key invalidates existing ciphertext, so set AMAVA_SECRET_KEY once
and keep it stable.
"""
from __future__ import annotations

import base64
import hashlib
import os
import warnings

from cryptography.fernet import Fernet

_ENV_VAR = "AMAVA_SECRET_KEY"
_DEFAULT_KEY_FILE = os.path.join("instance", "secret.key")


def _derive_fernet_key(secret: str) -> bytes:
    """Turn an arbitrary secret string into a valid 32-byte urlsafe Fernet key."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def load_or_create_key(key_file: str = _DEFAULT_KEY_FILE) -> bytes:
    env_secret = os.getenv(_ENV_VAR)
    if env_secret:
        return _derive_fernet_key(env_secret)

    if os.path.exists(key_file):
        with open(key_file, "rb") as fh:
            return fh.read().strip()

    # Dev convenience: generate and persist a key, with a loud warning.
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(key_file) or ".", exist_ok=True)
    with open(key_file, "wb") as fh:
        fh.write(key)
    warnings.warn(
        f"No {_ENV_VAR} set; generated a dev encryption key at {key_file}. "
        "Set AMAVA_SECRET_KEY in production and add the key file to .gitignore.",
        stacklevel=2,
    )
    return key


class SecretBox:
    """Symmetric encrypt/decrypt of UTF-8 strings."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_env(cls, key_file: str = _DEFAULT_KEY_FILE) -> "SecretBox":
        return cls(load_or_create_key(key_file))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
