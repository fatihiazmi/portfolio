# fatihiazmi.dev

Source for `fatihiazmi.dev`, a full-stack engineer's portfolio site.

The site runs on a Proxmox homelab behind Cloudflare. The `/stack` page shows it live.

## Layout

| Directory | Contents |
|---|---|
| `web/` | Public site: Astro with a React Three Fiber systems map. Hosted on Cloudflare Pages. |
| `admin/` | Admin SPA: Vue 3 + Vite. Served by the API at `/admin`. |
| `api/` | FastAPI + SQLite: projects, contact form, admin API, `/metrics`. |
| `infra/` | Docker Compose, Cloudflare Tunnel, Litestream, Prometheus, Grafana. |
| `docs/` | Intent, spec, plan, and setup guides. |

## Setup

```bash
uv tool install pre-commit
pre-commit install
```

Each commit runs `gitleaks` locally. CI runs it again on every push.

## Docs

- [Intent](docs/intent/portfolio.md)
- [Spec](docs/spec.md)
- [Plan](docs/plan.md)
