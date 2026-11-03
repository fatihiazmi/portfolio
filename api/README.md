# api

FastAPI + SQLite for `fatihiazmi.dev`. Spec: [`docs/spec.md`](../docs/spec.md) sections 6–9.

## Run

```bash
cd api
uv sync
uv run uvicorn portfolio_api.main:app --reload --port 8000
curl localhost:8000/api/health   # {"ok":true}
```

The database file defaults to `api/data/portfolio.db`. Migrations run at startup.

## Test and lint

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

## Config

Settings load from env vars or `api/.env`. The full list is in [`/.env.example`](../.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `data/portfolio.db` | SQLite file. Its directory is created on start. |
| `CORS_ORIGIN` | `http://localhost:4321` | The one origin allowed by CORS. Astro dev runs on port 4321. |

## Migrations

- Files: `src/portfolio_api/migrations/NNNN_name.sql`.
- Order: by file name. Applied versions are stored in `schema_migrations`.
- Each file runs in one transaction. A failure rolls the file back and stops startup.
- Forward-only. Fix a bad migration with a new file, never by editing an applied one.
- No triggers, and no `;` inside string literals. The splitter cuts statements at lines ending in `;`.
