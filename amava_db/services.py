"""Service/repository layer. All tenant-scoped access goes through here.

Three services, each constructed with an open Session:
  * UserService     - signup, login, API keys.
  * CredentialVault - encrypted per-user secrets (SP-API creds, supplier logins).
  * ScrapeStore     - scrape runs and their products, always scoped by user_id.

Kept free of any dependency on supplier_scraper (save_result duck-types the
result object) so the DB layer stays standalone.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .crypto import SecretBox
from .models import ApiKey, Credential, ScrapedProduct, ScrapeRun, User
from .security import (
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)

_PRODUCT_FIELDS = (
    "sku", "title", "price", "currency", "moq", "in_stock", "stock_quantity",
    "brand", "upc", "ean", "product_url", "image_url", "images", "category",
    "description", "specifications", "rating",
)


class UserService:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_user(self, email: str, password: str, *, role: str = "user") -> User:
        email = email.strip().lower()
        if self.get_by_email(email):
            raise ValueError(f"A user with email {email!r} already exists.")
        user = User(email=email, password_hash=hash_password(password), role=role)
        self.s.add(user)
        self.s.flush()  # assign id without ending the transaction
        return user

    def get(self, user_id: int) -> User | None:
        return self.s.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.s.scalar(select(User).where(User.email == email.strip().lower()))

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.get_by_email(email)
        if user and user.is_active and verify_password(password, user.password_hash):
            return user
        return None

    def issue_api_key(self, user_id: int, *, name: str = "default") -> tuple[ApiKey, str]:
        """Create an API key. Returns (record, raw_key); the raw key is only
        available here and is never stored."""
        raw, prefix, key_hash = generate_api_key()
        record = ApiKey(user_id=user_id, name=name, prefix=prefix, key_hash=key_hash)
        self.s.add(record)
        self.s.flush()
        return record, raw

    def verify_api_key(self, raw_key: str) -> User | None:
        record = self.s.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(raw_key), ApiKey.revoked.is_(False)
            )
        )
        if not record:
            return None
        record.last_used_at = datetime.now(timezone.utc)
        user = self.s.get(User, record.user_id)
        return user if user and user.is_active else None


class CredentialVault:
    """Encrypted secret storage. Payloads are JSON objects encrypted as one blob."""

    PROVIDER_SPAPI = "amazon_spapi"
    PROVIDER_SUPPLIER = "supplier"

    def __init__(self, session: Session, box: SecretBox) -> None:
        self.s = session
        self.box = box

    # -- generic ----------------------------------------------------------
    def _set(self, user_id: int, provider: str, label: str, payload: dict[str, Any]) -> None:
        ciphertext = self.box.encrypt(json.dumps(payload))
        existing = self.s.scalar(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.provider == provider,
                Credential.label == label,
            )
        )
        if existing:
            existing.ciphertext = ciphertext
        else:
            self.s.add(
                Credential(
                    user_id=user_id, provider=provider, label=label, ciphertext=ciphertext
                )
            )
        self.s.flush()

    def _get(self, user_id: int, provider: str, label: str) -> dict[str, Any] | None:
        record = self.s.scalar(
            select(Credential).where(
                Credential.user_id == user_id,
                Credential.provider == provider,
                Credential.label == label,
            )
        )
        if not record:
            return None
        return json.loads(self.box.decrypt(record.ciphertext))

    # -- typed helpers ----------------------------------------------------
    def set_spapi(
        self,
        user_id: int,
        *,
        lwa_client_id: str,
        lwa_client_secret: str,
        refresh_token: str,
        seller_id: str | None = None,
        marketplace: str = "US",
    ) -> None:
        self._set(user_id, self.PROVIDER_SPAPI, "", {
            "lwa_client_id": lwa_client_id,
            "lwa_client_secret": lwa_client_secret,
            "refresh_token": refresh_token,
            "seller_id": seller_id,
            "marketplace": marketplace,
        })

    def get_spapi(self, user_id: int) -> dict[str, Any] | None:
        return self._get(user_id, self.PROVIDER_SPAPI, "")

    def set_supplier_login(
        self, user_id: int, supplier: str, *, username: str, password: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {"username": username, "password": password}
        if extra:
            payload.update(extra)
        self._set(user_id, self.PROVIDER_SUPPLIER, supplier.lower(), payload)

    def get_supplier_login(self, user_id: int, supplier: str) -> dict[str, Any] | None:
        return self._get(user_id, self.PROVIDER_SUPPLIER, supplier.lower())


class ScrapeStore:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_run(
        self, user_id: int, supplier: str, *, source_url: str = "", transport: str | None = None
    ) -> ScrapeRun:
        run = ScrapeRun(
            user_id=user_id, supplier=supplier, source_url=source_url,
            transport=transport, status="running",
        )
        self.s.add(run)
        self.s.flush()
        return run

    def get_run(self, run_id: int) -> ScrapeRun | None:
        return self.s.get(ScrapeRun, run_id)

    def fail_run(self, run_id: int, error: str) -> None:
        run = self.s.get(ScrapeRun, run_id)
        if run:
            run.status = "error"
            run.error = error[:2000]
            run.finished_at = datetime.now(timezone.utc)

    def save_result(self, run_id: int, result: Any) -> int:
        """Persist a scrape result (duck-typed: needs .products, .pages_scraped,
        .transport_used, .errors). Returns the number of products saved."""
        run = self.s.get(ScrapeRun, run_id)
        if run is None:
            raise ValueError(f"ScrapeRun {run_id} not found")

        products = list(getattr(result, "products", []) or [])
        for p in products:
            self.s.add(ScrapedProduct(
                run_id=run.id,
                user_id=run.user_id,
                extra=dict(getattr(p, "extra", {}) or {}),
                **{f: getattr(p, f, None) for f in _PRODUCT_FIELDS},
            ))
        run.product_count = len(products)
        run.pages_scraped = int(getattr(result, "pages_scraped", 0) or 0)
        run.transport = getattr(result, "transport_used", None) or run.transport
        errors = getattr(result, "errors", None) or []
        run.status = "done"
        if errors:
            run.error = "; ".join(str(e) for e in errors)[:2000]
        run.finished_at = datetime.now(timezone.utc)
        self.s.flush()
        return len(products)

    def list_runs(self, user_id: int, *, limit: int = 50) -> list[ScrapeRun]:
        return list(self.s.scalars(
            select(ScrapeRun).where(ScrapeRun.user_id == user_id)
            .order_by(ScrapeRun.created_at.desc()).limit(limit)
        ))

    def list_products(
        self, user_id: int, *, supplier: str | None = None, limit: int = 100
    ) -> list[ScrapedProduct]:
        stmt = select(ScrapedProduct).where(ScrapedProduct.user_id == user_id)
        if supplier:
            stmt = stmt.join(ScrapeRun).where(ScrapeRun.supplier == supplier)
        stmt = stmt.order_by(ScrapedProduct.created_at.desc()).limit(limit)
        return list(self.s.scalars(stmt))
