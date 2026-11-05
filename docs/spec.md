# Spec: Portfolio Site v1

Source of intent: [`docs/intent/portfolio.md`](intent/portfolio.md).
Deadline: 2026-11-18.

## 1. Goals

- A freelance client understands what the owner builds within 60 seconds and finds the contact form.
- A hiring manager finds role fit, stack, and a resume within 30 seconds.
- The site itself proves platform skill: the `/stack` page shows the live system behind it.

## 2. Architecture

```
Visitor ──► Cloudflare edge (DNS, TLS, WAF, cache)
              ├─► Cloudflare Pages ── static site (Astro + React Three Fiber island)
              ├─► Tunnel (api.<domain>) ──► cloudflared ──► LXC "app" (Docker)
              │                                               ├─ FastAPI :8000 (/api, /admin, /metrics)
              │                                               └─ SQLite ──► Litestream ──► R2
              └─► Tunnel (grafana.<domain>, Access-gated) ──► LXC "obs" (Docker)
                                                              ├─ Prometheus (scrapes app, exporters)
                                                              ├─ Grafana (dashboards + alerting)
                                                              └─ exporters: pve, node, blackbox
Images: R2 bucket behind img.<domain>
```

| Part | Choice | Reason |
|---|---|---|
| Frontend | Astro, static output | Content pages ship zero JS. The 3D map loads as one island. |
| 3D | `@react-three/fiber` + `@react-three/drei` | The owner already writes React. Declarative scene code. |
| Styling | Tailwind CSS | Fast to build. Blueprint palette lives in tokens. |
| API | FastAPI, Python 3.12, `uv` | Owner's stack. Fits the Data and Platform direction. |
| Admin UI | Vue 3 + Vite SPA, PrimeVue components. FastAPI serves the build at `/admin`. | Needs real interactivity: map node editor, drag reorder, uploads. Same origin as the API, so no CORS. |
| Database | SQLite in WAL mode | One host, one writer. Fits the load. |
| Backup | Litestream to Cloudflare R2 | Continuous off-site replication. Restore in one command. |
| Exposure | Cloudflare Tunnel | No open ports. No static IP needed. Home IP stays hidden. |
| Admin auth | Cloudflare Access + JWT check in FastAPI | Gated at the edge, checked again at the app. |
| Spam control | Cloudflare Turnstile + honeypot field + rate limit | Free. No captcha puzzles for real clients. |
| Lead email | Resend free tier | One notification email per lead. |

### 2.1 Content flow

Project content lives in SQLite. The static site reads it at build time.

1. The owner edits a project in `/admin`.
2. The owner clicks **Publish**.
3. FastAPI calls the Cloudflare Pages deploy hook.
4. The Pages build fetches `GET /api/projects` and renders static pages.
5. The build commits nothing. It writes a snapshot to `web/src/data/projects.snapshot.json` in the build output only.

Failure rule: the build falls back to the snapshot committed in the repo when the API is unreachable. The site never goes blank because the homelab is down.

### 2.2 Homelab outage behaviour

| Feature | Behaviour when the homelab is down |
|---|---|
| All static pages and the 3D map | Stay up on Pages. |
| Contact form | Shows a `mailto:` link with the message pre-filled. The WhatsApp link stays up. |
| `/stack` | Shows "Homelab offline since <last seen>". This is honest and still a proof point. |
| Admin | Down. Acceptable. |

## 3. Pages

| Route | Purpose | Main content |
|---|---|---|
| `/` | Convert clients | Hero with the 3D systems map. Positioning line. "What I build" services block. Selected work list. Contact call to action. |
| `/work/[slug]` | Prove depth | Case study template, section 5. |
| `/stack` | Prove platform skill | Live metrics, section 7. Architecture diagram of this site. |
| `/contact` | Capture leads | Form, section 6. Also embedded on `/`. |
| `/resume` | Serve hiring managers | One-page HTML resume plus PDF download. |
| `/404` | Recover | Blueprint-styled "road closed" page with a link home. |

### 3.1 Home page order

1. Hero: name, positioning line, 3D map. Draft line: "Full-stack engineer. I build the systems organisations run their day on."
2. What I build: CMMS and maintenance, HR, payroll and overtime, ERP modules, government workflow systems.
3. How I work: AI-driven delivery, tests, production monitoring. Three short points, one with proof from each case study.
4. Selected work: SiMS, NADI, OTMS, then personal repos.
5. Contact call to action.

## 4. 3D systems map

### 4.1 Scene

- Ground: a blueprint grid. Thin lines, slow drift.
- Roads: edges between nodes. Light pulses travel along edges.
- Nodes, client projects: SiMS, NADI, OTMS. Large nodes.
- Nodes, personal projects: `ledger-engine`, `seatly`, `shieldwallet`. Small nodes.
- Edges: connect projects that share a domain or technique. Example: OTMS ↔ NADI (payroll, attendance).

### 4.2 Interaction

| Input | Result |
|---|---|
| Hover a node | Node glows. Label shows name and one-line summary. |
| Click a node | Camera flies to the node in about 800 ms. A side panel opens with summary, stack, and a "Read case study" link. |
| `Esc` or click empty space | Camera returns to the overview. |
| Pointer move | Slight camera parallax. |
| Keyboard `Tab` | Moves focus through nodes in list order. `Enter` opens the panel. |

### 4.3 Fallbacks and accessibility

- Every node also exists as an HTML list under the canvas. Screen readers and search engines read the list.
- `prefers-reduced-motion`: render one static frame. No drift, no pulses, no camera flights.
- No WebGL, or WebGL drawn in software (SwiftShader, llvmpipe): render a static SVG of the same map.
- Mobile: device pixel ratio capped at 1.5. Post-processing off.

### 4.4 Performance budget

| Metric | Target |
|---|---|
| Largest Contentful Paint, mid-range mobile | under 2.5 s |
| 3D island JS, gzipped | under 300 KB |
| 3D island load | After first paint, through `client:visible` |
| Frame rate, mid-range laptop | 60 fps |

## 5. Case study template

Each section maps to one database field, section 8.

1. Header: project name, client, year, role ("Builder"), stack tags.
2. Problem: what the client needed, in 2–4 sentences.
3. What I built: the modules or features the owner delivered.
4. Architecture: one SVG diagram.
5. Key decisions: 2–4 engineering decisions with the reason for each.
6. Screenshots: 3–6 images with captions.
7. Outcome: numbers where available, such as users, sites, records, or time saved.
8. Next step: contact call to action.

### 5.1 Screenshot rule

- Blur or replace every personal field before upload: names, MyKad numbers, payroll figures, phone numbers, addresses.
- Each image row carries a `scrubbed` flag. The owner sets it by hand after review.
- **Publish** is blocked while any image of the project has `scrubbed = false`.

## 6. Contact form

| Field | Type | Required |
|---|---|---|
| `name` | text, max 100 | yes |
| `email` | email | yes |
| `company` | text, max 150 | no |
| `kind` | `freelance` \| `hiring` \| `other` | yes |
| `budget` | `<RM10k` \| `RM10k–50k` \| `RM50k+` \| `unsure`. Shown only for `freelance`. | no |
| `message` | text, 20–5000 chars | yes |
| `website` | honeypot, hidden | must be empty |
| `turnstile_token` | Turnstile token | yes |

On submit:

1. Check the Turnstile token with Cloudflare.
2. Reject the request when `website` is not empty. Return 200 so bots learn nothing.
3. Rate limit: 5 submissions per IP per hour.
4. Store the lead. Store a salted hash of the IP, never the raw IP.
5. Send one notification email to the owner.
6. Show a confirmation: "Thanks. I reply within 2 working days."

WhatsApp: a `wa.me` link to `+60 11-5421 3066` sits above the form. It works when the homelab is down. WhatsApp leads skip SQLite and do not appear in the admin Leads screen.

## 7. `/stack` page

The page reads `GET /api/stack` in the browser every 30 seconds. FastAPI answers from Prometheus with a fixed allowlist of PromQL queries. Visitors never send a query.

| Panel | Source metric |
|---|---|
| API uptime, 30-day availability | `blackbox_exporter` probe of `/api/health` |
| Request rate and p95 latency, 24 h chart | FastAPI `/metrics` via `prometheus-client` |
| Host CPU, RAM, disk, 24 h chart | `prometheus-pve-exporter` |
| Tunnel status | `cloudflared` metrics endpoint |
| Last backup age | Litestream metrics endpoint |
| Deployed version | Git SHA baked in at build |
| Leads received | `portfolio_leads_total` counter. Count only, never content. |

The page also shows the architecture diagram from section 2. It also links to the Homelab Platform case study.

Security rules:

- The Proxmox exporter uses a read-only token with the `PVEAuditor` role. The token stays on the `obs` LXC.
- The Proxmox web UI never goes through the tunnel.
- Prometheus is never exposed through the tunnel.
- `/api/stack` returns numbers and time series only: no hostnames, no internal IPs, no labels that name hosts.

## 7a. Observability

### 7a.1 Components

| Component | Job |
|---|---|
| Prometheus | Scrapes every 30 s. Keeps 7 days of data on the 4 GB host, 15 days after the RAM upgrade. |
| Grafana | Dashboards and alerting. Private, behind Cloudflare Access at `grafana.<domain>`. |
| `prometheus-pve-exporter` | Proxmox host and LXC metrics. |
| `node_exporter` | Metrics for the `app` LXC. |
| `blackbox_exporter` | Probes the public site URL and `/api/health` through the internet, every 60 s. |
| FastAPI `/metrics` | Request count, latency histogram, `portfolio_leads_total`, `portfolio_contact_errors_total`. Reachable on the LAN only. |

### 7a.2 As code

Everything lives in `infra/obs/` and loads at container start:

- `prometheus.yml` with scrape targets
- `alerts/*.yml` alert rules
- `grafana/provisioning/` with data sources, dashboards as JSON, and contact points

No dashboard or alert is created by hand in the UI.

### 7a.3 Dashboards

| Dashboard | Panels |
|---|---|
| Site overview | Availability, request rate, p95 latency, error rate, leads |
| Homelab | Host CPU, RAM, disk, LXC status, network |
| Backups | Litestream lag, last snapshot age |

### 7a.4 Alerts

All alerts go to Telegram, with email as backup.

| Alert | Condition |
|---|---|
| `SiteDown` | Blackbox probe of `/api/health` fails for 3 minutes |
| `ContactErrors` | `portfolio_contact_errors_total` rises in 10 minutes |
| `BackupStale` | Last Litestream snapshot older than 1 hour |
| `DiskHigh` | Host disk above 85% for 15 minutes |
| `NewLead` | `portfolio_leads_total` rises. This one is informational. |

### 7a.5 Showcase

- The map gets a 7th node, **Homelab Platform**, kind `personal`. The `infra/` code is public on GitHub. Secrets are excluded.
- Its case study covers Proxmox, Cloudflare Tunnel, Litestream, the Prometheus and Grafana stack, alerts, and one real incident or restore drill.
- Screenshots of the Grafana dashboards go into that case study.

### 7a.6 Resources

| LXC | RAM now (4 GB host) | RAM after upgrade (12 GB host) | Disk |
|---|---|---|---|
| `app` | 512 MB | 1 GB | 8 GB |
| `obs` | 768 MB | 1.5 GB | 20 GB |

Prometheus retention: 7 days on the 4 GB host, 15 days after the upgrade.
Host capacity and the RAM upgrade decision are recorded in [`notes.md`](notes.md).

### 7a.7 Out of v1

Loki for logs, OpenTelemetry tracing.

## 8. Data model (SQLite)

```sql
CREATE TABLE projects (
  id          INTEGER PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  client      TEXT,
  kind        TEXT NOT NULL CHECK (kind IN ('client', 'personal')),
  year        INTEGER,
  summary     TEXT NOT NULL,
  problem_md  TEXT,
  built_md    TEXT,
  decisions_md TEXT,
  outcome_md  TEXT,
  stack       TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
  repo_url    TEXT,                          -- NULL for client projects
  diagram_key TEXT,                          -- R2 key of the SVG
  map_x       REAL, map_z REAL,              -- node position on the 3D map
  sort_order  INTEGER NOT NULL DEFAULT 0,
  published   INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT NOT NULL
);

CREATE TABLE project_edges (
  from_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  to_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label   TEXT,
  PRIMARY KEY (from_id, to_id)
);

CREATE TABLE project_images (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  r2_key     TEXT NOT NULL,
  alt        TEXT NOT NULL,
  caption    TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  scrubbed   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE leads (
  id         INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  name       TEXT NOT NULL,
  email      TEXT NOT NULL,
  company    TEXT,
  kind       TEXT NOT NULL CHECK (kind IN ('freelance', 'hiring', 'other')),
  budget     TEXT,
  message    TEXT NOT NULL,
  ip_hash    TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'replied', 'closed'))
);
```

## 9. API

### 9.1 Public

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness. Returns `{"ok": true}`. |
| GET | `/api/projects` | Published projects with edges and images. Used by the Pages build. |
| GET | `/api/projects/{slug}` | One published project. |
| POST | `/api/contact` | Create a lead, section 6. |
| GET | `/api/stack` | Live metrics, section 7. |

CORS allows the Pages origin only.

### 9.2 Admin

`/admin/*` (the Vue SPA) and `/api/admin/*` (its JSON API) sit behind Cloudflare Access. FastAPI also checks the `Cf-Access-Jwt-Assertion` header against the Access team's public keys. A request without a valid JWT gets 403.

#### SPA screens

| Screen | Purpose |
|---|---|
| Dashboard | New leads count, last publish, last backup. |
| Projects | List, create, edit, delete. Drag to reorder. Markdown fields with live preview. |
| Map editor | 2D top-down SVG grid. Drag nodes to set `map_x` and `map_z`. Click two nodes to add or remove an edge. |
| Images | Upload to R2 with preview. Set alt and caption. Toggle `scrubbed`. Drag to reorder. |
| Leads | List and filter by `kind` and `status`. Set status. |

#### JSON endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/summary` | Dashboard numbers. |
| GET, POST | `/api/admin/projects` | List all projects, including drafts. Create one. |
| GET, PATCH, DELETE | `/api/admin/projects/{id}` | Read, modify, remove one project. |
| PUT | `/api/admin/projects/order` | Save the project order. |
| PUT | `/api/admin/edges` | Replace the full edge list. |
| POST | `/api/admin/projects/{id}/images` | Upload one image to R2. |
| PATCH, DELETE | `/api/admin/images/{id}` | Modify alt, caption, order, `scrubbed`. Remove one image. |
| GET | `/api/admin/leads` | List leads with filters. |
| PATCH | `/api/admin/leads/{id}` | Set lead status. |
| POST | `/api/admin/publish` | Check the scrubbed rule. Call the Pages deploy hook. Returns 409 with the unscrubbed image IDs when the rule fails. |

## 10. Repository layout

```
portfolio/
├── web/        Astro site, 3D island, static fallback snapshot
├── admin/      Vue 3 + Vite SPA, built into api/static/admin
├── api/        FastAPI app, migrations, tests
├── infra/      docker-compose.yml, cloudflared config, litestream.yml, LXC setup notes
└── docs/       intent, spec, task plan
```

## 11. Security checklist

- The LXC runs unprivileged. Docker runs inside it.
- The tunnel routes `api.<domain>` to `http://api:8000` on the compose network only. The API port binds to `127.0.0.1` on the LXC.
- Secrets live in an `.env` file on the LXC, never in git: Turnstile secret, Resend key, R2 keys, Proxmox token, deploy hook URL, IP hash salt.
- All SQL uses bound parameters.
- Admin write requests must carry an `X-Requested-With: admin` header. FastAPI rejects writes without it. This blocks cross-site form posts that ride the Access cookie.
- Uploads accept `image/png`, `image/jpeg`, `image/webp`, and `image/svg+xml` only, max 5 MB. SVGs are sanitised before upload.
- Before launch: read the ISP terms on residential hosting. Not yet checked.

## 12. Acceptance criteria

- [ ] The site is live on the owner's domain by 2026-11-18.
- [ ] The home page shows the 3D map, services, work list, and contact call to action.
- [ ] Three case studies are published with scrubbed screenshots and diagrams.
- [ ] Three personal repos appear on the map with GitHub links.
- [ ] The Homelab Platform node and case study are published. The `infra/` code is public with no secrets.
- [ ] Grafana dashboards and alert rules load from git on a fresh `obs` container.
- [ ] Stopping the `app` LXC fires `SiteDown` to Telegram within 5 minutes.
- [ ] `grafana.<domain>` without Cloudflare Access login redirects to the Access login. The origin never serves Grafana to it.
- [ ] A test lead submitted from a phone arrives in SQLite and by email.
- [ ] `/admin` without Cloudflare Access login redirects to the Access login. The origin returns 403 to a request without a valid JWT.
- [ ] Stopping the LXC leaves the static site up, and the form switches to `mailto:`.
- [ ] A Litestream restore into a fresh directory produces a working database.
- [ ] `/stack` shows live metrics, and it shows the offline state when the LXC is stopped.
- [ ] Lighthouse mobile performance is 85 or higher on `/`.
- [ ] The reduced-motion and no-WebGL fallbacks render.

## 13. Open inputs from the owner

Due dates live in [`plan.md`](plan.md) section 4.

- Domain name
- Free RAM and disk on the Proxmox host, and the ISP verdict on hosting
- Email address for lead notifications
- Freelance budget bands in RM. Draft values are in section 6.
- Display name and positioning line
- Outcome numbers per case study: users, sites, records, time saved
- Scrubbed screenshots, 3–6 per client project
- Resume content
- Telegram bot token and chat ID for alerts
