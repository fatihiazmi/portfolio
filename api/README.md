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
| `IP_HASH_SALT` | empty | HMAC key for the lead IP hash. Empty: `/api/contact` returns 503. |
| `TURNSTILE_SECRET` | empty | Turnstile secret key. Empty: `/api/contact` returns 503. |
| `RESEND_API_KEY` | empty | Resend key. Empty: leads are stored, no email. |
| `LEAD_NOTIFY_EMAIL` | empty | Inbox for lead emails. Empty: no email. |
| `LEAD_FROM_EMAIL` | `fatihiazmi.dev <leads@fatihiazmi.dev>` | Sender on the Resend-verified domain. Another domain gets 403. |

Key setup: [`docs/guide/t9-contact-keys.md`](../docs/guide/t9-contact-keys.md).

## Public endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{"ok": true}`, or 503 when SQLite does not answer. |
| GET | `/api/projects` | `{"projects": [...], "edges": [{"source", "target", "label"}]}`. Published projects only, in `sort_order`. |
| GET | `/api/projects/{slug}` | One published project. 404 for an unknown slug and for a draft. |
| POST | `/api/contact` | `{"ok": true}`. Stores a lead and emails the owner. Spec section 6. |

Rules:

- Edges appear only when both ends are published.
- Images appear only when `scrubbed = 1`, even on a published project.
- `stack` is a JSON array. `diagram_url` and image `url` are built from `IMAGES_BASE_URL`.
- Internal columns stay out: `id`, `published`, `sort_order`, `diagram_key`.

## Contact

`POST /api/contact` runs these checks in order:

| Step | Check | Result on fail |
|---|---|---|
| 1 | Body fields, spec section 6 | 422 |
| 2 | Keys set | 503 `contact form is not configured` |
| 3 | Honeypot `website` filled | 200 `{"ok": true}`. Nothing stored, no Turnstile call. |
| 4 | Fewer than 5 leads from this IP hash in the last hour | 429 |
| 5 | Turnstile siteverify accepts the token | 400. Cloudflare unreachable: 502. |
| 6 | Store the lead | — |
| 7 | Resend email, after the response | Logged. The lead stays stored. |

Rules:

- The client IP comes from `CF-Connecting-IP`. Without it, from the socket peer.
- `ip_hash` is HMAC-SHA256 of the IP with `IP_HASH_SALT`. The raw IP is never stored.
- `budget` is stored only when `kind` is `freelance`.
- The email `reply_to` is the sender's address. Replying in the inbox answers the lead.

Local run with Cloudflare's always-pass test secret:

```bash
IP_HASH_SALT=dev TURNSTILE_SECRET=1x0000000000000000000000000000000AA \
  uv run uvicorn portfolio_api.main:app --reload --port 8000
```

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
