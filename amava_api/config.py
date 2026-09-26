"""API configuration from the environment. No secrets live here."""
from __future__ import annotations

import os


def _split(val: str) -> list[str]:
    return [v.strip() for v in val.split(",") if v.strip()]


# Where the ADK agent api_server runs (the old server proxied /run here too).
AGENT_BACKEND = os.getenv("AGENT_BACKEND", "http://localhost:1483")

# CORS: default permissive for local dev; lock down in prod via env.
CORS_ORIGINS = _split(os.getenv("AMAVA_CORS_ORIGINS", "*")) or ["*"]

# Where uploaded screenshots are stored (per-user subfolders are created).
SCREENSHOT_DIR = os.getenv("AMAVA_SCREENSHOT_DIR", "screenshots")

# Same port the old server.py used, so the existing frontend works unchanged.
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Phase 1 is single-tenant-by-default: all requests resolve to this local user
# until real auth (API key / JWT) is added. Created on first use.
DEV_USER_EMAIL = os.getenv("AMAVA_DEV_USER", "local@amava.dev")
