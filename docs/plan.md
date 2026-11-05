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
| T4 | 2 | API skeleton: FastAPI with `uv`, settings from env, `/api/health`, SQLite WAL, migrations for spec section 8, pytest setup. | T1 | `pytest` passes. `/api/health` returns `{"ok": true}` locally. | done |
| T5 | 2 | `app` LXC: unprivileged, Docker, compose for the API. Cloudflare Tunnel routes `api.<domain>` to `localhost:8000`. | T2, T3, T4 | `https://api.<domain>/api/health` returns 200 from a phone on mobile data. | done |
| T6 | 3 | Litestream replicates SQLite to R2. Run one restore drill. | T5 | A restore into a fresh directory opens and passes an integrity check. | done |
| T7 | 3 | Public read API: `/api/projects`, `/api/projects/{slug}`, CORS for the Pages origin. Seed script with 7 draft projects and edges. | T4 | Tests cover published-only filtering and 404 on an unknown slug. | done |
| T8 | 4 | Astro scaffold: Tailwind, blueprint colour tokens, base layout. Build-time fetch of projects with fallback to `projects.snapshot.json`. Deploy to Cloudflare Pages. Create the deploy hook. | T2, T7 | Pages serves the site on the domain. A build with the API stopped still succeeds from the snapshot. | done |
| T9 | 4–5 | Contact: `POST /api/contact` with Turnstile, honeypot, rate limit, IP hash, Resend email. Form component with `kind`-dependent budget field and `mailto:` fallback. | T7, T8 | A test lead from a phone lands in SQLite and in the inbox. Honeypot and rate-limit tests pass. | done |
| T10 | 5 | Home page sections: hero with map placeholder, What I build, How I work, Selected work list, contact call to action. **Owner input:** display name and positioning line. | T8 | All sections render with real copy on mobile and desktop. | done |
| T11 | 6–7 | 3D map island: blueprint grid, nodes from project data, edges with light pulses, hover label, click camera flight, side panel, `Esc` to return, keyboard focus, HTML list under the canvas. | T10 | All interactions in spec section 4.2 work with mouse and keyboard. | done |
| T12 | 7 | Map fallbacks and performance: reduced-motion static frame, no-WebGL SVG, mobile DPR cap, `client:visible` load. | T11 | 3D island under 300 KB gzipped. Both fallbacks render. | done |
| T13 | 8 | Case study page `/work/[slug]` per spec section 5. `/resume` page with PDF link. `/404` "road closed" page. | T8 | One seeded project renders every template section. | done |
| T14 | 8 | Admin auth: Cloudflare Access apps for `/admin*` and `/api/admin*`. FastAPI middleware checks the Access JWT and the `X-Requested-With: admin` header on writes. | T5 | Requests without login get 403. Tests cover a missing JWT, a bad JWT, and a write without the header. | done |
| T15 | 8 | **Owner input:** outcome numbers and 3–6 scrubbed screenshots for each of SiMS, NADI, and OTMS. One SVG architecture diagram each, drafted with Claude. | — | Files are in a local `content/` directory, outside git. | todo |
| T16 | 9 | Admin JSON API per spec section 9.2: projects, order, edges, R2 image upload, leads, summary, publish with scrub gate and deploy hook. | T7, T14 | Tests cover every endpoint. Publish returns 409 with unscrubbed image IDs. | done |
| T17 | 9–10 | Vue admin SPA with PrimeVue: Dashboard, Projects with markdown preview and drag reorder, Images, Leads. Build into `api/static/admin`. | T16 | The owner edits a project, uploads an image, and publishes through the UI. | done |
| T18 | 10 | Vue map editor: 2D SVG grid, drag nodes to set `map_x` and `map_z`, click two nodes to toggle an edge. | T17 | Positions and edges saved in the editor show on the live 3D map after publish. | done |
| T19 | 10–11 | Content entry: 3 client case studies and 3 personal projects in the admin, with images, captions, alt text, and diagrams. Mark every image `scrubbed` after a second review. Publish. | T13, T15, T17 | 6 project pages live. Every screenshot checked by eye for personal data. | done |
| T20 | 11 | `obs` LXC: Prometheus, `prometheus-pve-exporter` with a `PVEAuditor` token, `node_exporter`, `blackbox_exporter`. FastAPI `/metrics` with request, latency, and lead counters. | T3, T5 | All targets show `up` in Prometheus. | done |
| T21 | 12 | Grafana as code: data source, 3 dashboards, 5 alert rules, Telegram contact point. Cloudflare Tunnel and Access for `grafana.<domain>`. **Owner input:** Telegram bot token and chat ID. | T20 | A fresh `obs` container loads everything from git. `grafana.<domain>` returns 403 without login. | done |
| T22 | 12 | `/api/stack` with the PromQL allowlist. `/stack` page with live panels, 24 h charts, offline state, and the site architecture diagram. | T8, T20 | `/stack` shows live data, and it shows the offline state when the `app` LXC stops. | done |
| T23 | 13 | Homelab Platform: make `infra/` public with a full secrets scan. Write the case study with Grafana screenshots and one restore or outage drill. Publish as the 7th node. | T19, T21, T22 | Node and case study live. Secret scan on the public repo is clean. | done |
| T24 | 14 | Acceptance run: every check in spec section 12. Lighthouse mobile on `/`. Stop the `app` LXC and confirm the `SiteDown` alert. | T6, T9, T12, T18, T19, T23 | Every check passes, or each failure has a fix task in T25. | done |
| T25 | 14–15 | Fix the failures found in T24. | T24 | Every T24 failure is resolved or moved to v2 with a written reason. | done |
| T26 | 15 | Launch: save a fresh `projects.snapshot.json` in the repo. Final publish. **Owner:** post the link on LinkedIn and send it to warm contacts. | T25 | Site live on the domain on 2026-11-18. | todo |

### T24 results and T25 fix list

Acceptance run on 2026-11-05 against spec section 12, deployed `b7e7995`.

| Check | Result | Evidence |
|---|---|---|
| Site live on the domain | pass | `/`, `/stack`, `/resume` 200. `www` 301 to apex. Unknown path 404. |
| Home page sections | pass | Hero, map, `#services`, `#how`, `#work`, `#contact` in the HTML. 3D canvas renders. |
| 3 case studies, scrubbed screenshots, diagrams | pass | `sims` 5, `nadi` 6, `otms` 5 images. 0 unscrubbed in SQLite. All 27 image and diagram URLs 200. |
| 3 personal repos with GitHub links | pass | `ledger-engine`, `seatly`, `shieldwallet` pages link their repos. Each repo URL 200. |
| Homelab node, public `infra/`, no secrets | pass | `homelab-platform` page 200, 4 images. Secret scan from T23 clean. |
| Grafana loads from git on a fresh container | pass | Throwaway Grafana 13.2.4 from `git archive HEAD`: 3 dashboards, 5 rules, 3 contact points, 1 template, 0 errors. |
| `SiteDown` to Telegram within 5 min | pass, see F3 | `pct stop 202` 07:45:21Z. Pending 07:46:40Z. Firing 07:49:28Z. Sent after 30 s `group_wait`, about 4 min 37 s. Owner received the Telegram message. |
| `grafana.<domain>` 403 without login | pass, see F2 | Edge returns 302 to the Access login. |
| Test lead from a phone | pass | Lead 4 in SQLite at 08:05:58Z, `POST /api/contact` 200. Owner received the email. |
| `/admin` 403 without login | pass, see F2 | Edge returns 302 to the Access login. Origin returns 403. |
| LXC stopped: static site up, form `mailto:` | pass | `/` 200. Form logged `mailto mode: health probe failed`. Mail label and note shown. |
| Litestream restore | pass | `restore-drill.sh` 07:40:21Z: integrity `ok`, 8 tables match. |
| `/stack` live, and offline with LXC stopped | pass | `data-state` `live`, then `offline` with "Homelab offline". |
| Lighthouse mobile 85+ on `/` | **fail, F1** | Performance 67 in 3 runs. Accessibility, best practices, SEO 100. |
| Reduced-motion and no-WebGL fallbacks | pass | Reduced motion: 0 draw calls after the first frame. No WebGL: SVG map, no scene download, list opens the panel. |

| ID | Failure | Cause | Fix |
|---|---|---|---|
| F1 | Lighthouse mobile performance 67 on `/`, target 85. | `scene.*.js` draws every frame. Lab Chrome renders WebGL in software, so each frame costs about 150 ms. Total Blocking Time 4–8.6 s. The SVG fallback alone scores 99. | Stop the render loop when nothing moves, or start the 3D scene on first interaction on mobile. Re-run Lighthouse 3 times. |
| F2 | Spec says 403 for `/admin` and `grafana.<domain>` without login. The edge returns 302 to the Access login. | Cloudflare Access redirects browsers to its login page. The origin still returns 403. | Change the spec 12 wording to "redirects to the Access login, and the origin returns 403". |
| F3 | `SiteDown` worst case is about 5.5 min, over the 5 min target. The measured run took 4 min 37 s. | Probe 60 s + rule evaluation 60 s + `for: 3m` + `group_wait` 30 s. | Set `group_wait: 0s` for `SiteDown` and cut `for` to `2m30s`. Repeat the stop test. |

T25 results, deployed `d185909` on 2026-11-05:

| ID | Status | Commit | Evidence |
|---|---|---|---|
| F1 | resolved | `67eb680` | Software WebGL (SwiftShader, llvmpipe) keeps the SVG map. Live Lighthouse mobile: 99, 99, 99. TBT 0 ms. A hardware GPU name still loads the 3D scene. Reduced motion with a hardware GPU still draws one frame. |
| F2 | resolved | `d185909` | Spec 12 now says the edge redirects to the Access login, and the origin returns 403. |
| F3 | resolved | `45b0ca0` | Probe every 30 s, `group_wait` 0s, `for` stays 3 min. Worst case about 4.5 min. Stop test: `pct stop 202` 08:18:54Z, sent 08:22:28Z, 3 min 34 s. |

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
