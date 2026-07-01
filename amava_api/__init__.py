"""AMAVA backend API.

A clean, multi-tenant FastAPI app that replaces the old single-user server.py.
It serves the SAME endpoint contract the frontend (Amava-v2) already expects,
on the same port (51483), but backed by the new stack:

  * amava_db        - users, encrypted credential vault, scrape storage
  * amava_agent     - ADK agent + per-user orchestration (run_supplier_scrape)
  * supplier_scraper- the scraping engine
  * sp_api_amazon   - Amazon SP-API client (per-user creds from the vault)

Run it:
    python -m amava_api            # uvicorn on 0.0.0.0:51483

NO credentials are hardcoded. SP-API endpoints read per-user creds from the
encrypted vault and return a clean "not connected" until those are set.
"""
from __future__ import annotations

from .app import create_app

__all__ = ["create_app"]
