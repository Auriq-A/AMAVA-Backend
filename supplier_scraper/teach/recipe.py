"""Supplier recipes: what Teach Mode records and how it is persisted.

A ``SupplierRecipe`` is everything the wizard learns by watching the user drive
the browser once: the login page + form selectors, the products page, how many
products to fetch, and which fields to extract. On replay the scraper reuses
this plus the saved session cookies, so it never has to ask again.

Persistence is twofold (per the product decision):
  * Disk  - a human-readable recipe JSON + the session cookies, under instance/.
  * DB    - the recipe + credentials + cookies, encrypted in the credential
            vault (amava_db). Best-effort: if amava_db isn't importable we just
            keep the disk copy and say so.
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def domain_of(url: str) -> str:
    """Bare host for keying a recipe (e.g. 'app.avasam.com')."""
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "_", domain.lower()).strip("_") or "site"


@dataclass
class SupplierRecipe:
    """A learned, replayable scraping plan for one supplier domain."""

    domain: str
    start_url: str
    products_url: str
    login_url: str | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    # CSS selector matching one product card on the listing page (learned by
    # the user clicking a product). Replay waits for + counts these, since many
    # catalogs (e.g. avasam) render products as non-anchor cards.
    product_selector: str | None = None
    min_products: int = 50
    fields: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def requires_login(self) -> bool:
        return bool(self.login_url and self.username_selector and self.password_selector)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupplierRecipe":
        known = {k: data.get(k) for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)


class RecipeStore:
    """Reads/writes recipes and session cookies under a base directory.

    Layout:
        <base>/recipes/<domain>.json    - the recipe (no secrets)
        <base>/sessions/<domain>.json   - Playwright storage_state (cookies)

    The sessions dir holds auth cookies and should be git-ignored.
    """

    def __init__(self, base_dir: str | Path = "instance") -> None:
        self.base = Path(base_dir)
        self.recipes_dir = self.base / "recipes"
        self.sessions_dir = self.base / "sessions"

    # -- recipes ----------------------------------------------------------
    def recipe_path(self, domain: str) -> Path:
        return self.recipes_dir / f"{_slug(domain)}.json"

    def save_recipe(self, recipe: SupplierRecipe) -> Path:
        self.recipes_dir.mkdir(parents=True, exist_ok=True)
        path = self.recipe_path(recipe.domain)
        path.write_text(json.dumps(recipe.to_dict(), indent=2), encoding="utf-8")
        return path

    def load_recipe(self, domain: str) -> SupplierRecipe | None:
        path = self.recipe_path(domain)
        if not path.exists():
            return None
        return SupplierRecipe.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # -- sessions (cookies) ----------------------------------------------
    def session_path(self, domain: str) -> Path:
        return self.sessions_dir / f"{_slug(domain)}.json"

    def save_session(self, domain: str, storage_state: dict[str, Any]) -> Path:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self.session_path(domain)
        path.write_text(json.dumps(storage_state), encoding="utf-8")
        return path

    def load_session(self, domain: str) -> dict[str, Any] | None:
        path = self.session_path(domain)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def save_to_vault(
    recipe: SupplierRecipe,
    *,
    username: str | None,
    password: str | None,
    storage_state: dict[str, Any] | None,
    user_email: str = "local@amava.dev",
) -> tuple[int | None, str | None]:
    """Persist the recipe + credentials + cookies, encrypted, in amava_db.

    Returns (user_id, error). On any failure (amava_db missing, etc.) returns
    (None, message) so the caller can fall back to the disk copy gracefully.
    """
    try:
        from amava_db import CredentialVault, Database, SecretBox, UserService
    except Exception as exc:  # noqa: BLE001
        return None, f"amava_db not available ({exc}); saved to disk only."

    try:
        db = Database()
        db.create_all()
        box = SecretBox.from_env()
        with db.session() as s:
            users = UserService(s)
            user = users.get_by_email(user_email)
            if user is None:
                # Local dev owner for standalone teaching runs. Random password;
                # this account is only a key for the credential vault.
                user = users.create_user(user_email, secrets.token_urlsafe(24))
            vault = CredentialVault(s, box)
            vault.set_supplier_login(
                user.id,
                recipe.domain,
                username=username or "",
                password=password or "",
                extra={
                    "recipe": recipe.to_dict(),
                    "storage_state": storage_state or {},
                },
            )
            return user.id, None
    except Exception as exc:  # noqa: BLE001
        return None, f"DB save failed ({exc}); saved to disk only."


def load_from_vault(
    domain: str, *, user_email: str = "local@amava.dev"
) -> tuple[SupplierRecipe | None, dict[str, str] | None, dict[str, Any] | None]:
    """Inverse of ``save_to_vault``: returns (recipe, creds, storage_state).

    ``creds`` is ``{"username", "password"}`` (for re-login when a saved
    session has expired). Any failure returns (None, None, None).
    """
    try:
        from amava_db import CredentialVault, Database, SecretBox, UserService
    except Exception:  # noqa: BLE001
        return None, None, None

    try:
        db = Database()
        box = SecretBox.from_env()
        with db.session() as s:
            user = UserService(s).get_by_email(user_email)
            if user is None:
                return None, None, None
            blob = CredentialVault(s, box).get_supplier_login(user.id, domain)
        if not blob:
            return None, None, None
        recipe = SupplierRecipe.from_dict(blob["recipe"]) if blob.get("recipe") else None
        creds = {"username": blob.get("username", ""), "password": blob.get("password", "")}
        storage_state = blob.get("storage_state") or None
        return recipe, creds, storage_state
    except Exception:  # noqa: BLE001
        return None, None, None
