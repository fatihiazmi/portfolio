# syntax=docker/dockerfile:1
# Build context: `api/`. The admin SPA comes from the named context `admin-src` (`admin/`).
# Compose passes it. Plain docker: docker build --build-context admin-src=admin api

# Admin SPA (plan T17). Type checks run in dev with `pnpm build`. The image only bundles.
FROM node:24.13.1-slim AS admin
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /admin
COPY --from=admin-src package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY --from=admin-src . .
RUN pnpm exec vite build --outDir /out --emptyOutDir

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home-dir /app app \
 && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=build --chown=app:app /app /app
COPY --from=admin --chown=app:app /out /app/static/admin
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 DATABASE_PATH=/data/portfolio.db
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"
# One worker: SQLite has one writer, and the app holds one connection.
CMD ["uvicorn", "portfolio_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header"]
