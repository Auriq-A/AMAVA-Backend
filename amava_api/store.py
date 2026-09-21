"""Per-user app-state storage for the ungating / scraping flow blobs.

The old server kept scraped data, checked data and search keys in memory + an
ad-hoc sqlite file (single user). Here they're rows in one ``app_state`` table,
scoped by ``user_id`` and stored as JSON, so the flow is multi-tenant.

The model attaches to amava_db's declarative Base, so ``Database.create_all()``
creates this table alongside the rest — no separate migration.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from amava_db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppState(Base):
    __tablename__ = "app_state"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_app_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AppStateStore:
    """Get/set/delete JSON blobs keyed by (user_id, key)."""

    # Well-known keys.
    SCRAPED = "scraped"        # {"raw_string", "items_count", "saved_at"}
    CHECKED = "checked"        # {"results", "skipped", "timestamp", "unit"}
    SEARCH_KEY = "search_key"  # {"data", "unit", "saved_at"}
    AMAZON_STATUS = "amazon_check_status"
    FBA_RESULTS = "fba_profit_results"

    def __init__(self, session) -> None:
        self.s = session

    def set(self, user_id: int, key: str, value: Any) -> None:
        row = self.s.scalar(
            select(AppState).where(AppState.user_id == user_id, AppState.key == key)
        )
        payload = json.dumps(value)
        if row:
            row.value = payload
        else:
            self.s.add(AppState(user_id=user_id, key=key, value=payload))
        self.s.flush()

    def get(self, user_id: int, key: str) -> Any | None:
        row = self.s.scalar(
            select(AppState).where(AppState.user_id == user_id, AppState.key == key)
        )
        if not row or not row.value:
            return None
        try:
            return json.loads(row.value)
        except json.JSONDecodeError:
            return None

    def delete(self, user_id: int, key: str) -> None:
        row = self.s.scalar(
            select(AppState).where(AppState.user_id == user_id, AppState.key == key)
        )
        if row:
            self.s.delete(row)
            self.s.flush()
