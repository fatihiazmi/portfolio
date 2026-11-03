# Intent: Portfolio Site

Confirmed with the owner on 2026-11-03.

| Field | Intent |
|---|---|
| Outcome | A portfolio that shows authority and credibility. Every visit ends in "contact me". |
| User | Freelance clients come first: organisations that run operational systems. Hiring managers come second. |
| Why now | The owner is actively looking for clients. |
| Success | Live by 2026-11-18. Leads arrive through the contact form, tagged `freelance` or `hiring`. |
| Shape | Blueprint feel: a calm, precise Three.js systems map. Projects are nodes on a road-and-network grid. Fun lives in the details. |
| Content | Case studies for SiMS, NADI, and OTMS with real screenshots and architecture diagrams. Public personal repos sit beside them: `ledger-engine`, `seatly`, `shieldwallet`. |
| Features | Contact form, admin, and a live `/stack` page that shows how the site runs. |
| Platform showcase | Prometheus and Grafana on the homelab, configured as code. Shown as a 7th map node, "Homelab Platform", with its own case study. Added 2026-11-03. Fills the gap of having no Platform Engineer project. |
| Infra | Frontend on Cloudflare Pages. FastAPI and SQLite in a Proxmox LXC behind Cloudflare Tunnel. Litestream backs SQLite up to R2. Cloudflare Access gates the admin. |
| Constraint | 15 days. Running cost about USD 10 a year, the domain only. |
| Out of scope (v1) | Blog, lab or playground section, easter eggs, Malay translation, visitor analytics dashboard, a CMS beyond project entries, Loki logs, and tracing. |

## Owner profile

- Role: full-stack engineer. Practices AI-driven development.
- Languages: JavaScript/TypeScript, Python, PHP.
- Possible next roles: Data Engineer, Platform Engineer, Principal Engineer.
- Personality read: a rigorous systems builder who has fun with it.
- Role on the highlight projects: builder, not lead.

## Disclosure rules

- Client and project names: allowed.
- Client code: never shown or linked.
- Real screenshots: allowed. Blur or replace every personal field first: names, MyKad numbers, payroll, phone numbers, addresses.

Tracking: the task plan carries a `Status` column (`todo`, `in progress`, `done`). Each task's commit sets its row to `done`.
