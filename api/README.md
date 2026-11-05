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
| `CF_ACCESS_TEAM_DOMAIN` | empty | Access team domain, `<team>.cloudflareaccess.com`. Empty: admin returns 503. |
| `CF_ACCESS_AUD` | empty | AUD tag of the `portfolio-admin` Access application. Empty: admin returns 503. |
| `ADMIN_EMAIL` | empty | The one email allowed into admin. Empty: admin returns 503. |
| `R2_ACCOUNT_ID` | empty | Cloudflare account ID. Any `R2_*` empty: uploads return 503. |
| `R2_IMAGES_BUCKET` | empty | Images bucket, `portfolio-images`. |
| `R2_ACCESS_KEY_ID` | empty | R2 token scoped to the images bucket. |
| `R2_SECRET_ACCESS_KEY` | empty | Secret of the same token. |
| `PAGES_DEPLOY_HOOK_URL` | empty | Pages deploy hook. Empty: publish returns 503. |
| `ADMIN_UI_DIR` | `api/static/admin` | Admin SPA build. No `index.html` there: `/admin/` returns 503. |
| `METRICS_PORT` | `0` | Port for Prometheus `/metrics`. `0`: off. Compose sets `9464`. |
| `METRICS_HOST` | `0.0.0.0` | Address the metrics server binds inside the container. |
| `PROMETHEUS_URL` | empty | Prometheus on the `obs` LXC, `http://192.168.0.152:9090`. Empty: `/api/stack` returns 503, `last_backup_at` is null. |

Key setup: [`docs/guide/t9-contact-keys.md`](../docs/guide/t9-contact-keys.md), [`docs/guide/t14-cloudflare-access.md`](../docs/guide/t14-cloudflare-access.md), [`docs/guide/t16-r2-images.md`](../docs/guide/t16-r2-images.md).

## Public endpoints

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{"ok": true}`, or 503 when SQLite does not answer. |
| GET | `/api/projects` | `{"projects": [...], "edges": [{"source", "target", "label"}]}`. Published projects only, in `sort_order`. |
| GET | `/api/projects/{slug}` | One published project. 404 for an unknown slug and for a draft. |
| POST | `/api/contact` | `{"ok": true}`. Stores a lead and emails the owner. Spec section 6. |
| GET | `/api/stack` | Live numbers for the `/stack` page. Spec section 7. See [Stack](#stack). |

Rules:

- Edges appear only when both ends are published.
- Images appear only when `scrubbed = 1`, even on a published project.
- `stack` is a JSON array. `diagram_url` and image `url` are built from `IMAGES_BASE_URL`.
- Internal columns stay out: `id`, `published`, `sort_order`, `diagram_key`.

## Metrics

`GET /metrics` runs on `METRICS_PORT`, never on the API port. The tunnel routes the API port only. Compose publishes the metrics port on the LAN address in `METRICS_BIND`. Spec 7a.1, plan T20.

| Metric | Type | Labels |
|---|---|---|
| `portfolio_http_requests_total` | counter | `method`, `route` (route template, `other` when no route matches), `status` |
| `portfolio_http_request_duration_seconds` | histogram | `method`, `route`. Ends at the last response byte. Background tasks are excluded. |
| `portfolio_leads_total` | counter | none. Count only, never lead content. |
| `portfolio_contact_errors_total` | counter | `reason`: `not_configured`, `turnstile_unavailable`, `email_failed`. All start at 0. |

## Stack

`GET /api/stack` answers from Prometheus with the fixed queries in `src/portfolio_api/stack.py`. Spec section 7, plan T22.

Rules:

- The route takes no parameters. Visitors never send a query.
- Every query aggregates to one series. `prometheus.py` drops all labels, so no host name or IP leaves the API. A query that returns more than one series logs an error and gives `null`.
- One response is cached for 30 s and shared by every visitor. Browsers get `Cache-Control: no-store`, so an outage shows at once.
- Prometheus down (network error, 3 s timeout, 5xx): 503 `{"detail": "metrics offline"}`. The error is cached for 30 s too.

| Field | Source |
|---|---|
| `api_probe_up` | Blackbox probe of `/api/health` from the internet |
| `availability.ratio` | Same probe, averaged over `window_days` (7). Spec 7 asks for 30 days. Prometheus keeps 7 on the 4 GB host. |
| `tunnel_connections` | `cloudflared_tunnel_ha_connections` of the public tunnel. Healthy: 4. |
| `backup.lag_seconds` | `portfolio:litestream_backup_lag_seconds`. 0: in sync. |
| `backup.last_upload_at` | Last Litestream upload to R2 in 7 days. Null: no database change in that time. |
| `host.cpu`, `host.memory`, `host.disk` | Proxmox host, `prometheus-pve-exporter`. Ratios, 0 to 1. |
| `leads_total` | `COUNT(*)` on `leads` in SQLite. The `portfolio_leads_total` counter resets on every API restart, so it is not a total. |
| `series` | 24 h, one point per 10 min, 145 points. `requests_per_hour` leaves out `/api/health`. `latency_p95_ms` keeps it. |

## Admin gate

`src/portfolio_api/admin_auth.py` checks every request to `/admin*` and `/api/admin*`. Spec section 9.2.

| Step | Check | Result on fail |
|---|---|---|
| 1 | `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, and `ADMIN_EMAIL` set | 503 |
| 2 | `Cf-Access-Jwt-Assertion` header present | 403 |
| 3 | RS256 signature from the team certs, `aud`, `iss`, `exp`, `iat` | 403 |
| 4 | JWT `email` equals `ADMIN_EMAIL`, any case | 403 |
| 5 | POST, PUT, PATCH, DELETE carry `X-Requested-With: admin` | 403 |

Rules:

- Team keys are cached for 1 hour. An unknown `kid` refetches them, at most once a minute.
- A certs fetch error keeps the old keys and never grants access.
- `GET /api/admin/me` returns `{"email": ...}` for the logged-in admin.

## Admin endpoints

All sit behind the admin gate. Writes need `X-Requested-With: admin`. Spec section 9.2.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/admin/summary` | — | Lead and project counts, `blocking_images`, `last_publish`. `last_backup_at` is `null` until T22. |
| GET | `/api/admin/projects` | — | `{"projects": [...], "edges": [{"from_id", "to_id", "label"}]}`. Drafts and unscrubbed images included. |
| POST | `/api/admin/projects` | Project fields. `slug`, `title`, `kind`, `summary` required. | 201 with the project. 409 on a used slug. |
| GET | `/api/admin/projects/{id}` | — | One project with its images. |
| PATCH | `/api/admin/projects/{id}` | Any project fields. `null` clears a nullable field. | The project. 409 on a used slug. |
| DELETE | `/api/admin/projects/{id}` | — | 204. Removes its edges, image rows, and R2 objects. |
| PUT | `/api/admin/projects/order` | `{"ids": [...]}`, every project id once | 204. `sort_order` becomes 10, 20, 30... |
| PUT | `/api/admin/edges` | `{"edges": [{"from_id", "to_id", "label"}]}` | The new edge list. Replaces every edge. |
| POST | `/api/admin/projects/{id}/images` | Multipart: `file`, `alt`, optional `caption` | 201 with the image, `scrubbed: false`. |
| PUT | `/api/admin/projects/{id}/diagram` | Multipart: `file`, SVG only | The project with the new `diagram_key`. The old object is removed. |
| PATCH | `/api/admin/images/{id}` | Any of `alt`, `caption`, `sort_order`, `scrubbed` | The image. |
| DELETE | `/api/admin/images/{id}` | — | 204. On an R2 error: 502, and the row stays. |
| GET | `/api/admin/leads` | Query: `kind`, `status`, `limit` (1–200, default 50), `offset` | `{"leads": [...], "total": n}`, newest first. No IP hash. |
| PATCH | `/api/admin/leads/{id}` | `{"status": "new" \| "replied" \| "closed"}` | The lead. |
| POST | `/api/admin/publish` | — | The publish record. 409 with `image_ids` when the scrub rule fails. |

Field rules:

- `slug`: lowercase letters, digits, and single hyphens, max 60.
- `stack`: up to 20 tags, 1–40 chars each.
- `repo_url`: `http://` or `https://` only.
- `map_x`, `map_z`: −100 to 100.
- An empty string in an optional text field is stored as `NULL`.
- Unknown fields: 422.

Uploads (spec section 11):

- Types: PNG, JPEG, WebP, SVG. The type comes from the file bytes, never from the name or `Content-Type`. Anything else: 415.
- Size: 5 MB max. Larger: 413.
- SVG: parsed with `defusedxml`. A DTD is rejected. Elements outside an SVG drawing allowlist are removed: `script`, `foreignObject`, `a`, animation. `on*` attributes, external `href`, external `url(...)`, and `@import` are removed.
- JPEG EXIF is not stripped. Phone photos can carry GPS. Upload screenshots, not photos.
- Keys: `<slug>/<16 hex>.<ext>`, diagrams `<slug>/diagram-<16 hex>.svg`. Objects are cached for one year, so a key never changes content.
- The file goes to R2 before the row is written. An R2 error returns 502 and stores nothing.

Publish:

1. `PAGES_DEPLOY_HOOK_URL` empty: 503.
2. Any image of a published project has `scrubbed = 0`: 409 `{"detail", "image_ids"}`. Draft projects never block.
3. POST to the deploy hook. An error: 502. The hook URL never appears in the response or the log.
4. Each hook call adds a row to `publishes`.

## Admin UI

FastAPI serves the Vue build from `ADMIN_UI_DIR` at `/admin`. The admin gate runs first. Source and dev setup: [`admin/README.md`](../admin/README.md).

| Path | Returns |
|---|---|
| `/admin` | 307 to `/admin/`. |
| `/admin/assets/*` | The file, cached for one year. Names carry a content hash. |
| `/admin/<file>` | The file, `Cache-Control: no-cache`. A missing path with an extension: 404. |
| Any other `/admin/*` | `index.html`, so the Vue router handles the path. |

The image builds the SPA in its own stage. Locally, `pnpm build` in `admin/` writes the build to `api/static/admin`.

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
