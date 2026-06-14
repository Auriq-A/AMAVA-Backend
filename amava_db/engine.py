"""Database engine + session management.

A thin Database wrapper holds the engine and hands out sessions via a context
manager that commits on success and rolls back on error. Default URL is a local
SQLite file; set AMAVA_DATABASE_URL to point at Postgres in production.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

DEFAULT_DATABASE_URL = "sqlite:///amava_saas.db"


def database_url() -> str:
    return os.getenv("AMAVA_DATABASE_URL", DEFAULT_DATABASE_URL)


class Database:
    def __init__(self, url: str | None = None, *, echo: bool = False) -> None:
        self.url = url or database_url()
        # SQLite needs check_same_thread=False to be used from async/worker threads.
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(
            self.url, echo=echo, future=True, connect_args=connect_args
        )
        self._Session = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        """Create tables if they don't exist (lightweight migration for dev)."""
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
