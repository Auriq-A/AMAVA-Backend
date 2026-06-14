"""Process-wide singletons: the database and the encryption box.

Created lazily on first use so importing the agent/tools performs no I/O and
needs no secret key until a tool actually runs.
"""
from __future__ import annotations

from amava_db import Database, SecretBox

_db: Database | None = None
_box: SecretBox | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
        _db.create_all()  # dev-time auto-migration; no-op if tables exist
    return _db


def get_box() -> SecretBox:
    global _box
    if _box is None:
        _box = SecretBox.from_env()
    return _box
