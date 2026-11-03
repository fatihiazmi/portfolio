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
| `IMAGES_BASE_URL` | `https://img.fatihiazmi.dev` | Base URL for image and diagram keys in R2. |

## Public endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{"ok": true}`, or 503 when SQLite does not answer. |
| GET | `/api/projects` | `{"projects": [...], "edges": [{"source", "target", "label"}]}`. Published projects only, in `sort_order`. |
| GET | `/api/projects/{slug}` | One published project. 404 for an unknown slug and for a draft. |

Rules:

- Edges appear only when both ends are published.
- Images appear only when `scrubbed = 1`, even on a published project.
- `stack` is a JSON array. `diagram_url` and image `url` are built from `IMAGES_BASE_URL`.
- Internal columns stay out: `id`, `published`, `sort_order`, `diagram_key`.

## Seed

```bash
uv run python -m portfolio_api.seed             # 7 draft projects and their edges
uv run python -m portfolio_api.seed --publish   # local dev only: seeded rows are published
```

The seed inserts by `slug` and never overwrites an existing row. All seed text is a draft. The owner replaces it in T19.

On the `app` LXC:

```bash
docker compose -f /opt/portfolio/infra/app/docker-compose.yml exec api python -m portfolio_api.seed
```

## Migrations

- Files: `src/portfolio_api/migrations/NNNN_name.sql`.
- Order: by file name. Applied versions are stored in `schema_migrations`.
- Each file runs in one transaction. A failure rolls the file back and stops startup.
- Forward-only. Fix a bad migration with a new file, never by editing an applied one.
- No triggers, and no `;` inside string literals. The splitter cuts statements at lines ending in `;`.
