# Guide: Check Proxmox Host Capacity (T3)

Goal: know whether the host can run the two new LXCs.
Time: 10 minutes.

## 1. What the site needs

| LXC | RAM | Disk | Cores |
|---|---|---|---|
| `app` (FastAPI, SQLite, Litestream, cloudflared) | 1 GB | 8 GB | 1 |
| `obs` (Prometheus, Grafana, exporters) | 1.5 GB | 20 GB | 1 |
| **Total** | **2.5 GB** | **28 GB** | **2** |

## 2. Read the numbers

Open a shell on the Proxmox host: **Node → Shell** in the web UI, or SSH.

### RAM

```bash
free -h
```

Read the `available` column on the `Mem:` row.

Running guests can grow up to their limits. Sum those limits:

```bash
pvesh get /cluster/resources --type vm --output-format json \
  | jq -r '.[] | select(.status=="running") | "\(.name)\t\(.maxmem/1073741824) GB"'
```

If `jq` is missing, run `apt install jq`.

Headroom = total RAM − sum of running guest limits − 1 GB for the host itself.

### Disk

```bash
pvesm status
```

Read the `Available` column for the storage that holds container disks. This is usually `local-lvm` or a ZFS pool. The value is in KiB. Divide by 1048576 for GiB.

### CPU and version

```bash
nproc
pveversion
```

### LXC template

T5 uses a Debian 12 template. Check it now:

```bash
pveam update
pveam available --section system | grep debian-12
```

## 3. Decide

| Result | Action |
|---|---|
| Headroom ≥ 2.5 GB RAM and ≥ 28 GB disk | Proceed with the plan. |
| Headroom ≥ 1 GB RAM, < 2.5 GB | Build `app` now. Shut down an unused guest before T20, or cut T21 per plan section 3. |
| Headroom < 1 GB RAM | Stop. Free memory on the host, or run the `app` LXC on a small VPS instead. Tell Claude before T5. |

## 4. Record

Add to `docs/notes.md` under **Proxmox host**: total RAM, headroom, storage name and free disk, cores, `pveversion` output, and the decision.

Done when: `docs/notes.md` holds the numbers and the decision.
