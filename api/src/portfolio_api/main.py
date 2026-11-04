import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from portfolio_api import admin, admin_projects, admin_ui, contact, projects
from portfolio_api.admin_auth import AccessVerifier, admin_gate
from portfolio_api.config import Settings, get_settings
from portfolio_api.db import connect, migrate
from portfolio_api.r2 import R2

log = logging.getLogger("portfolio_api")


HTTP_TIMEOUT = httpx.Timeout(10.0)


def create_app(settings: Settings | None = None, http: httpx.Client | None = None) -> FastAPI:
    """Build the app. Tests pass `http` with a mock transport for Turnstile, Resend, and Access."""
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
        if settings.admin_ready:
            app.state.access = AccessVerifier(settings, client)
        else:
            log.warning("admin off: set CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD, and ADMIN_EMAIL")
        app.state.r2 = R2(settings, client) if settings.images_ready else None
        if app.state.r2 is None:
            log.warning("image uploads off: set the R2_* keys for the images bucket")
        if not settings.pages_deploy_hook_url:
            log.warning("publish off: set PAGES_DEPLOY_HOOK_URL")
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

    app.middleware("http")(admin_gate)
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
    app.include_router(admin.router)
    app.include_router(admin_projects.router)
    app.include_router(admin_ui.router)

    return app


app = create_app()
