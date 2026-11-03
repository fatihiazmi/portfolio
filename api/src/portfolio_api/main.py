import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from portfolio_api import projects
from portfolio_api.config import Settings, get_settings
from portfolio_api.db import connect, migrate

log = logging.getLogger("portfolio_api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = connect(settings.database_path)
        applied = migrate(conn)
        if applied:
            log.info("applied migrations: %s", ", ".join(applied))
        app.state.db = conn
        app.state.settings = settings
        try:
            yield
        finally:
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

    return app


app = create_app()
