"""AMAVA multi-tenant persistence layer.

SQLAlchemy 2.0 models + service layer for a real multi-user SaaS:
users/API keys, an encrypted per-user credential vault, and scrape storage -
every row scoped by user_id. SQLite by default, Postgres by URL swap.

    from amava_db import Database, SecretBox, UserService, CredentialVault, ScrapeStore

    db = Database(); db.create_all()
    box = SecretBox.from_env()
    with db.session() as s:
        user = UserService(s).create_user("a@b.com", "pw")
        CredentialVault(s, box).set_spapi(user.id, lwa_client_id="...",
            lwa_client_secret="..", refresh_token="..")
"""
from __future__ import annotations

from .crypto import SecretBox, load_or_create_key
from .engine import Database, database_url
from .models import (
    ApiKey,
    Base,
    Credential,
    ScrapedProduct,
    ScrapeRun,
    User,
)
from .services import CredentialVault, ScrapeStore, UserService

__all__ = [
    "Database",
    "database_url",
    "SecretBox",
    "load_or_create_key",
    # models
    "Base",
    "User",
    "ApiKey",
    "Credential",
    "ScrapeRun",
    "ScrapedProduct",
    # services
    "UserService",
    "CredentialVault",
    "ScrapeStore",
]
