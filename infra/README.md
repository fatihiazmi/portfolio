# infra

| Directory | Runs on | Contents | Task |
|---|---|---|---|
| `app/` | LXC 202 `portfolio-app` | API + cloudflared | T5 |
| Litestream | LXC 202 | SQLite backup to R2 | T6 |
| `obs/` | LXC `obs` | Prometheus, Grafana, exporters | T20, T21 |

## `app` LXC

| Setting | Value |
|---|---|
| VMID / hostname | `202` / `portfolio-app` |
| Template | `debian-12-standard_12.12-1_amd64` |
| Resources | 1 core, 512 MB RAM, 512 MB swap, 8 GB on `local-lvm` |
| Mode | Unprivileged, `nesting=1,keyctl=1` (needed for Docker), start on boot |
| Network | `vmbr0`, static LAN address, gateway `192.168.0.1` |
| Repo checkout | `/opt/portfolio` |
| SQLite data | `/var/lib/portfolio/data`, owned by UID `10001` (container user `app`) |
| Secrets | `/opt/portfolio/infra/app/.env`, mode `600` |

### Public route

Cloudflare Zero Trust → Tunnels → `portfolio` → public hostname:
`api.fatihiazmi.dev` → `HTTP` → `api:8000`.

The API port binds to `127.0.0.1:8000` on the LXC. Only the tunnel reaches it from outside.

### Deploy a new version

From the Proxmox host shell:

```bash
pct exec 202 -- bash -c 'cd /opt/portfolio && git pull --ff-only && cd infra/app && docker compose up -d --build'
```

### Check

```bash
curl -s https://api.fatihiazmi.dev/api/health          # {"ok":true}
pct exec 202 -- docker compose -f /opt/portfolio/infra/app/docker-compose.yml ps
pct exec 202 -- docker compose -f /opt/portfolio/infra/app/docker-compose.yml logs --tail 50 api
```

### Rotate the tunnel token

1. Cloudflare dashboard → tunnel `portfolio` → refresh the token.
2. On the LXC, replace the `CLOUDFLARED_TUNNEL_TOKEN=` line in `.env`.
3. Run `docker compose up -d cloudflared`.

### Memory at idle (2026-11-03)

| Process | RAM |
|---|---|
| `api` container | about 40–60 MB |
| `cloudflared` container | about 26 MB |
| Whole LXC | about 207 MB used of 512 MB |
