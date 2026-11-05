# infra

| Directory | Runs on | Contents | Task |
|---|---|---|---|
| `app/` | LXC 202 `portfolio-app` | API + cloudflared | T5 |
| `app/litestream.yml` | LXC 202 `portfolio-app` | SQLite backup to R2 | T6 |
| `obs/` | LXC 203 `portfolio-obs` | Prometheus, exporters, Grafana, tunnel `obs` | T20, T21 |

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

The build also bundles the admin SPA from `admin/` (plan T17). Compose passes it through `additional_contexts`, which needs Docker Compose 2.17 or later on the LXC.

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
| `litestream` container | about 29 MB |
| Whole LXC | about 183–207 MB used of 512 MB |

## Backups (Litestream)

| Setting | Value |
|---|---|
| Image | `litestream/litestream:0.5.17`, service `litestream` in `app/docker-compose.yml` |
| Config | `app/litestream.yml` |
| Source | `/var/lib/portfolio/data/portfolio.db` |
| Replica | R2 bucket `portfolio-backup`, prefix `portfolio/` |
| Snapshots | Every 1 h, kept 7 days. WAL changes sync about every 1 s. |
| Keys | `app/.env.litestream`. R2 token scoped to the backup bucket only. Guide: `docs/guide/t6-r2-backup.md`. |
| Metrics | `192.168.0.151:9090/metrics` on the LAN. Prometheus scrapes it. Recording rules: `portfolio:litestream_backup_lag_seconds` (0 when current) and `portfolio:litestream_last_upload_timestamp_seconds`. |

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

### Drill log

| Date | Result |
|---|---|
| 2026-11-03 | Passed. Integrity `ok`. A lead written 5 s before the restore was present in the restored copy. |
| 2026-11-05 | Passed in 6.8 s. Integrity `ok`. Row counts match on all 8 tables: 7 projects, 16 images, 3 leads. |

## Metrics on the `app` LXC

Plan T20. Each port publishes on `METRICS_BIND` from `app/.env`, set to `192.168.0.151`. Unset: loopback only, and Prometheus cannot scrape.

| Port | Source | Path |
|---|---|---|
| 9464 | API, `prometheus-client` | `/metrics` |
| 9090 | Litestream | `/metrics` |
| 2000 | cloudflared | `/metrics` |
| 9100 | `node_exporter` service `node-exporter` | `/metrics` |

The tunnel routes `api:8000` only. No metrics port goes through it.

The API also reads Prometheus for `/api/stack` (plan T22). `PROMETHEUS_URL` in `app/.env` is `http://192.168.0.152:9090`. The `obs` stack publishes Prometheus on `PROM_BIND`, the `obs` LAN address.

## `obs` LXC

| Setting | Value |
|---|---|
| VMID / hostname | `203` / `portfolio-obs` |
| Template | `debian-12-standard_12.12-1_amd64` |
| Resources | 2 cores, 768 MB RAM, 512 MB swap, 20 GB on `local-lvm`. Lean limits, spec 7a.6. |
| Mode | Unprivileged, `nesting=1,keyctl=1`, start on boot |
| Network | `vmbr0`, `192.168.0.152/24`, gateway `192.168.0.1` |
| Docker | `download.docker.com` apt repo, same as LXC 202 |
| Repo checkout | `/opt/portfolio` |
| Secrets | `/opt/portfolio/infra/obs/.env`, mode `600` |
| Prometheus | `192.168.0.152:9090` on the LAN. Never through a tunnel. Data in volume `obs_prometheus-data`. |
| Grafana | `127.0.0.1:3000` on the LXC. Outside: `https://grafana.fatihiazmi.dev` through tunnel `obs`, behind Access app `portfolio-grafana`. Data in volume `obs_grafana-data`. |

### Services

| Service | Image | Memory limit | Job |
|---|---|---|---|
| `prometheus` | `prom/prometheus:v3.15.1` | 192 MB | Scrapes every 30 s. Keeps 7 days or 4 GB. |
| `pve-exporter` | `prompve/prometheus-pve-exporter:3.10.1` | 96 MB | Proxmox host and guest metrics |
| `blackbox` | `prom/blackbox-exporter:v0.29.1` | 32 MB | Probes `https://fatihiazmi.dev/` and `/api/health` every 60 s |
| `grafana` | `grafana/grafana:13.2.4` | 384 MB | Dashboards and alerts, all from `grafana/` |
| `cloudflared` | `cloudflare/cloudflared:2026.10.7` | 64 MB | Tunnel `obs`: `grafana.fatihiazmi.dev` → `grafana:3000` |

The limits add up to the 768 MB of the LXC. Grafana 13 uses about 300 MB at idle.

### Grafana as code

| Path | Contents |
|---|---|
| `grafana/provisioning/datasources/` | Prometheus, uid `prometheus` |
| `grafana/provisioning/dashboards/` | Provider for folder `Portfolio` |
| `grafana/dashboards/*.json` | Site overview, Homelab, Backups. Generated by `grafana/build_dashboards.py`. Never edit the JSON by hand. |
| `grafana/provisioning/alerting/` | Contact points, notification policy, 5 alert rules, message template |
| `grafana/emails/ng_alert_notification.{html,txt}` | Alert email layout in the site's blueprint colours. Mounted over Grafana's own. Subject set inline in `contact-points.yml`. |

Provisioned items are read-only in the UI. Change the file, commit, deploy, then run `docker compose restart grafana`.

The email layout overrides a Grafana file. After a Grafana upgrade, send a test email and check it renders. Grafana renders the `.txt` part with HTML escaping too, so it prints values through `__dangerouslyInjectHTML`.

Login: Access sends its JWT in `Cf-Access-Jwt-Assertion`. Grafana checks the signature against the team's keys, the issuer, and the `portfolio-grafana` AUD. The email in `ADMIN_EMAIL` gets the Admin role. Any other email gets no role. Break-glass: user `admin`, password `GRAFANA_ADMIN_PASSWORD`, at `127.0.0.1:3000` on the LXC.

### Alerts

| Alert | Fires when | Goes to |
|---|---|---|
| `SiteDown` | `/api/health` probe fails for 3 min, or the probe series is gone | Telegram and email |
| `ContactErrors` | `portfolio_contact_errors_total` rises in 10 min | Telegram and email |
| `BackupStale` | `portfolio:litestream_backup_lag_seconds` above 15 min for 5 min, or absent | Telegram and email |
| `DiskHigh` | A host disk or Proxmox storage above 85% for 15 min | Telegram and email |
| `NewLead` | `portfolio_leads_total` rises | Telegram only, no resolve message |

`BackupStale` watches backup lag, not snapshot age as in spec 7a.4. Litestream 0.5 uploads only when data changes. On a quiet site the last upload gets old while the backup stays current. Lag is how long the newest change has waited for an upload. Rules: `prometheus/rules/backup.yml`. Email goes through Resend SMTP from `alerts@fatihiazmi.dev`. Keys: [`docs/guide/t21-grafana-alerts.md`](../docs/guide/t21-grafana-alerts.md).

### Proxmox token

| Setting | Value |
|---|---|
| User | `prometheus@pve`, realm `pve`, no password |
| ACL | `PVEAuditor` on `/` |
| Token | `prometheus@pve!obs`, privilege separation off, so it has the user's read-only rights |
| Stored | `infra/obs/.env` on LXC 203 only |

Rotate the token from the Proxmox host shell:

```bash
pveum user token remove prometheus@pve obs
pveum user token add prometheus@pve obs --privsep 0 --output-format json
```

Put the new `value` in the `PVE_TOKEN_VALUE=` line of `infra/obs/.env`. Then run `docker compose up -d pve-exporter` on LXC 203.

### Deploy

From the Proxmox host shell:

```bash
pct exec 203 -- bash -c 'cd /opt/portfolio && git pull --ff-only && cd infra/obs && docker compose up -d'
```

After a change to `prometheus.yml` or a rule file, reload without a restart:

```bash
pct exec 203 -- docker compose -f /opt/portfolio/infra/obs/docker-compose.yml kill -s HUP prometheus
```

### Check

Before a commit, run `infra/obs/check.sh` locally. It runs `promtool` in Docker. It checks the config and the rules, and runs the rule tests in `infra/obs/tests/`.

On the LXC, every target must show `up`:

```bash
pct exec 203 -- curl -s 'http://192.168.0.152:9090/api/v1/query?query=up'
```
