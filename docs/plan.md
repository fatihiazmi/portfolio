# Plan: Portfolio Site v1

Sources: [`intent/portfolio.md`](intent/portfolio.md), [`spec.md`](spec.md).
Window: Day 1 = 2026-11-04 (Wed). Day 15 = 2026-11-18 (Wed), launch day.
Sizing: about 4 focused hours per day. The owner's daily hours are unconfirmed. If fewer hours are available, apply the cut order in section 3.

## 1. Overview

| ID | Day | Task | Depends | Done when | Status |
|---|---|---|---|---|---|
| T1 | 1 | Create the monorepo: `web/`, `admin/`, `api/`, `infra/`, `docs/`. Add `.gitignore`, `.env.example`, pre-commit with a secret scanner. Push to GitHub. | — | Repo on GitHub. Secret scan runs on commit. | done |
| T2 | 1 | **Owner input:** buy the domain. Move DNS to Cloudflare. | — | Zone is active in Cloudflare. | done |
| T3 | 1 | **Owner input:** record free RAM and disk on the Proxmox host. Read the ISP terms on residential hosting. | — | Numbers, capacity decision, and ISP verdict written in `docs/notes.md`. Guides: `docs/guide/t3-proxmox-capacity.md`, `docs/guide/t3-isp-terms.md`. | done |
| T4 | 2 | API skeleton: FastAPI with `uv`, settings from env, `/api/health`, SQLite WAL, migrations for spec section 8, pytest setup. | T1 | `pytest` passes. `/api/health` returns `{"ok": true}` locally. | todo |
| T5 | 2 | `app` LXC: unprivileged, Docker, compose for the API. Cloudflare Tunnel routes `api.<domain>` to `localhost:8000`. | T2, T3, T4 | `https://api.<domain>/api/health` returns 200 from a phone on mobile data. | todo |
| T6 | 3 | Litestream replicates SQLite to R2. Run one restore drill. | T5 | A restore into a fresh directory opens and passes an integrity check. | todo |
| T7 | 3 | Public read API: `/api/projects`, `/api/projects/{slug}`, CORS for the Pages origin. Seed script with 7 draft projects and edges. | T4 | Tests cover published-only filtering and 404 on an unknown slug. | todo |
| T8 | 4 | Astro scaffold: Tailwind, blueprint colour tokens, base layout. Build-time fetch of projects with fallback to `projects.snapshot.json`. Deploy to Cloudflare Pages. Create the deploy hook. | T2, T7 | Pages serves the site on the domain. A build with the API stopped still succeeds from the snapshot. | todo |
| T9 | 4–5 | Contact: `POST /api/contact` with Turnstile, honeypot, rate limit, IP hash, Resend email. Form component with `kind`-dependent budget field and `mailto:` fallback. | T7, T8 | A test lead from a phone lands in SQLite and in the inbox. Honeypot and rate-limit tests pass. | todo |
| T10 | 5 | Home page sections: hero with map placeholder, What I build, How I work, Selected work list, contact call to action. **Owner input:** display name and positioning line. | T8 | All sections render with real copy on mobile and desktop. | todo |
| T11 | 6–7 | 3D map island: blueprint grid, nodes from project data, edges with light pulses, hover label, click camera flight, side panel, `Esc` to return, keyboard focus, HTML list under the canvas. | T10 | All interactions in spec section 4.2 work with mouse and keyboard. | todo |
| T12 | 7 | Map fallbacks and performance: reduced-motion static frame, no-WebGL SVG, mobile DPR cap, `client:visible` load. | T11 | 3D island under 300 KB gzipped. Both fallbacks render. | todo |
| T13 | 8 | Case study page `/work/[slug]` per spec section 5. `/resume` page with PDF link. `/404` "road closed" page. | T8 | One seeded project renders every template section. | todo |
| T14 | 8 | Admin auth: Cloudflare Access apps for `/admin*` and `/api/admin*`. FastAPI middleware checks the Access JWT and the `X-Requested-With: admin` header on writes. | T5 | Requests without login get 403. Tests cover a missing JWT, a bad JWT, and a write without the header. | todo |
| T15 | 8 | **Owner input:** outcome numbers and 3–6 scrubbed screenshots for each of SiMS, NADI, and OTMS. One SVG architecture diagram each, drafted with Claude. | — | Files are in a local `content/` directory, outside git. | todo |
| T16 | 9 | Admin JSON API per spec section 9.2: projects, order, edges, R2 image upload, leads, summary, publish with scrub gate and deploy hook. | T7, T14 | Tests cover every endpoint. Publish returns 409 with unscrubbed image IDs. | todo |
| T17 | 9–10 | Vue admin SPA with PrimeVue: Dashboard, Projects with markdown preview and drag reorder, Images, Leads. Build into `api/static/admin`. | T16 | The owner edits a project, uploads an image, and publishes through the UI. | todo |
| T18 | 10 | Vue map editor: 2D SVG grid, drag nodes to set `map_x` and `map_z`, click two nodes to toggle an edge. | T17 | Positions and edges saved in the editor show on the live 3D map after publish. | todo |
| T19 | 10–11 | Content entry: 3 client case studies and 3 personal projects in the admin, with images, captions, alt text, and diagrams. Mark every image `scrubbed` after a second review. Publish. | T13, T15, T17 | 6 project pages live. Every screenshot checked by eye for personal data. | todo |
| T20 | 11 | `obs` LXC: Prometheus, `prometheus-pve-exporter` with a `PVEAuditor` token, `node_exporter`, `blackbox_exporter`. FastAPI `/metrics` with request, latency, and lead counters. | T3, T5 | All targets show `up` in Prometheus. | todo |
| T21 | 12 | Grafana as code: data source, 3 dashboards, 5 alert rules, Telegram contact point. Cloudflare Tunnel and Access for `grafana.<domain>`. **Owner input:** Telegram bot token and chat ID. | T20 | A fresh `obs` container loads everything from git. `grafana.<domain>` returns 403 without login. | todo |
| T22 | 12 | `/api/stack` with the PromQL allowlist. `/stack` page with live panels, 24 h charts, offline state, and the site architecture diagram. | T8, T20 | `/stack` shows live data, and it shows the offline state when the `app` LXC stops. | todo |
| T23 | 13 | Homelab Platform: make `infra/` public with a full secrets scan. Write the case study with Grafana screenshots and one restore or outage drill. Publish as the 7th node. | T19, T21, T22 | Node and case study live. Secret scan on the public repo is clean. | todo |
| T24 | 14 | Acceptance run: every check in spec section 12. Lighthouse mobile on `/`. Stop the `app` LXC and confirm the `SiteDown` alert. | T6, T9, T12, T18, T19, T23 | Every check passes, or each failure has a fix task in T25. | todo |
| T25 | 14–15 | Fix the failures found in T24. | T24 | Every T24 failure is resolved or moved to v2 with a written reason. | todo |
| T26 | 15 | Launch: save a fresh `projects.snapshot.json` in the repo. Final publish. **Owner:** post the link on LinkedIn and send it to warm contacts. | T25 | Site live on the domain on 2026-11-18. | todo |

### Tracking rules

- Start a task: set its status to `in progress`.
- Finish a task: set its status to `done` in the task's own commit.
- Pick the next task: the first `todo` row whose dependencies are all `done`.
- Commit subjects end with the task ID, for example `feat(api): add contact endpoint (T9)`.

## 2. Critical path

T4 → T7 → T8 → T10 → T11 → T12 → T24 → T25 → T26

The 3D map (T11, T12) carries the most risk. If T11 is not `done` by the end of Day 7, cut the light pulses and camera flight first.

## 3. Cut order

If the schedule slips, cut in this order. Each item moves to v2. The launch date stays fixed.

| Order | Cut | What remains |
|---|---|---|
| 1 | T23 Homelab Platform case study | Ships after launch. `/stack` still runs live. |
| 2 | T21 Grafana and alerts | The external uptime check from UptimeRobot replaces the alerts. Prometheus still feeds `/stack`. |
| 3 | T18 Vue map editor | The owner types `map_x` and `map_z` in the project form. |
| 4 | Light pulses and camera flight in T11 | A static 3D map with hover labels and click-to-open panels. |
| 5 | `/resume` HTML page in T13 | PDF link only. |

Never cut: contact form (T9), case studies (T19), screenshot scrubbing, admin auth (T14), backups (T6).

## 4. Owner inputs by day

| Day | Input |
|---|---|
| 1 | Domain bought. Proxmox free RAM and disk. ISP terms read. |
| 4 | Lead notification email. Freelance budget bands in RM. |
| 5 | Display name and positioning line. |
| 8 | Outcome numbers and scrubbed screenshots for SiMS, NADI, OTMS. |
| 10 | Resume content. |
| 10 | 8 GB DDR4-2400 SODIMM installed in the Proxmox host. Without it, T20 runs on lean limits. |
| 12 | Telegram bot token and chat ID. |
