"""FastAPI app factory: wires CORS, ensures tables, mounts routers."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import store  # noqa: F401 - registers the AppState table on amava_db.Base
from .config import CORS_ORIGINS
from .deps import get_db
from .routers import agent, auth, credentials, scraping, screenshots, sales


def create_app() -> FastAPI:
    app = FastAPI(title="AMAVA API", version="2.0.0")

    # CORS: '*' can't be combined with credentials per the spec, so only enable
    # credentials when specific origins are configured.
    allow_credentials = CORS_ORIGINS != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create all tables (users, credentials, scrape storage, app_state).
    get_db().create_all()

    app.include_router(auth.router)
    app.include_router(agent.router)
    app.include_router(credentials.router)
    app.include_router(scraping.router)
    app.include_router(screenshots.router)
    app.include_router(sales.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "amava_api"}

    return app


app = create_app()
