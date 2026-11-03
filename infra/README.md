# infra

| Directory | Runs on | Contents | Task |
|---|---|---|---|
| `app/` | LXC 202 `portfolio-app` | API + cloudflared | T5 |
| `app/litestream.yml` | LXC 202 `portfolio-app` | SQLite backup to R2 | T6 |
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
| Secrets | `/opt/portfolio/infra/app/.env` and `.env.litestream`, both mode `600` |

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

## Backups (Litestream)

| Setting | Value |
|---|---|
| Image | `litestream/litestream:0.5.17`, service `litestream` in `app/docker-compose.yml` |
| Config | `app/litestream.yml` |
| Source | `/var/lib/portfolio/data/portfolio.db` |
| Replica | R2 bucket `portfolio-backup`, prefix `portfolio/` |
| Snapshots | Every 1 h, kept 7 days. WAL changes sync about every 1 s. |
| Keys | `app/.env.litestream`. R2 token scoped to the backup bucket only. Guide: `docs/guide/t6-r2-backup.md`. |
| Metrics | `litestream:9090/metrics` on the compose network. Scraped in T20. |

Litestream keeps its state in `/var/lib/portfolio/data/.portfolio.db-litestream/`. Never remove it while the stack runs.

### Restore drill

Run monthly, and after any change to `litestream.yml`:

```bash
pct exec 202 -- /opt/portfolio/infra/app/restore-drill.sh
```

The script restores the latest replica into a fresh `/tmp` directory and runs `PRAGMA integrity_check`. It compares row counts per table with the live database. Exit `0` means passed. Exit `2` means row counts differ, often from a write in the last second. Run it again.

### Recover after data loss

Use this when the live database is gone or corrupt.

```bash
pct enter 202
cd /opt/portfolio/infra/app
docker compose stop api litestream
mv /var/lib/portfolio/data /var/lib/portfolio/data.broken.$(date +%s)
install -d -o 10001 -g 10001 /var/lib/portfolio/data
docker run --rm --user 10001:10001 --env-file .env.litestream \
  -v "$PWD/litestream.yml:/etc/litestream.yml:ro" -v /var/lib/portfolio/data:/data \
  litestream/litestream:0.5.17 restore -config /etc/litestream.yml -integrity-check full /data/portfolio.db
docker compose up -d
curl -s https://api.fatihiazmi.dev/api/health
```

For a point in time, add `-timestamp 2026-11-05T10:00:00Z` before `/data/portfolio.db`. Restores reach back 7 days.
