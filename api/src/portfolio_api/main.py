import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from portfolio_api import contact, projects
from portfolio_api.config import Settings, get_settings
from portfolio_api.db import connect, migrate

log = logging.getLogger("portfolio_api")


HTTP_TIMEOUT = httpx.Timeout(10.0)


def create_app(settings: Settings | None = None, http: httpx.Client | None = None) -> FastAPI:
    """Build the app. Tests pass `http` with a mock transport for Turnstile and Resend."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = connect(settings.database_path)
        applied = migrate(conn)
        if applied:
            log.info("applied migrations: %s", ", ".join(applied))
        if not settings.contact_ready:
            log.warning("contact form off: set IP_HASH_SALT and TURNSTILE_SECRET")
        client = http or httpx.Client(timeout=HTTP_TIMEOUT)
        app.state.db = conn
        app.state.settings = settings
        app.state.http = client
        try:
            yield
        finally:
            if http is None:
                client.close()
            conn.close()

    app = FastAPI(title="portfolio-api", lifespan=lifespan, docs_url=None, redoc_url=None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health")
    def health() -> JSONResponse:
        """Liveness for the blackbox probe. Returns 503 when SQLite does not answer."""
        try:
            app.state.db.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            log.exception("health check: database error")
            return JSONResponse({"ok": False}, status_code=503)
        return JSONResponse({"ok": True})

    app.include_router(projects.router)
    app.include_router(contact.router)

    return app


app = create_app()
