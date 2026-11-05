"""Build the Grafana dashboards as JSON. Spec 7a.3, plan T21.

Run after a change, then commit the JSON:

    python3 infra/obs/grafana/build_dashboards.py

`infra/obs/check.sh` fails when the committed JSON differs from this output.
Standard library only.
"""

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
DS = {"type": "prometheus", "uid": "prometheus"}

# Proxmox guest and node series carry `id` only. `pve_guest_info` adds the guest `name`.
WITH_NAME = '* on (id) group_left (name) pve_guest_info{id=~"lxc/.+"}'


def target(expr: str, legend: str = "", ref: str = "A", instant: bool = False) -> dict:
    return {
        "refId": ref,
        "datasource": DS,
        "expr": expr,
        "legendFormat": legend or "__auto",
        "instant": instant,
        "range": not instant,
    }


def thresholds(*steps: tuple[float | None, str]) -> dict:
    return {
        "mode": "absolute",
        "steps": [{"value": v, "color": c} for v, c in steps],
    }


GREEN = thresholds((None, "green"))


def stat(
    title: str,
    expr: str,
    unit: str = "short",
    steps: dict = GREEN,
    decimals: int | None = None,
    mappings: list | None = None,
    legend: str = "",
    description: str = "",
) -> dict:
    defaults: dict = {"unit": unit, "thresholds": steps, "color": {"mode": "thresholds"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    if mappings:
        defaults["mappings"] = mappings
    return {
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": DS,
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "colorMode": "background",
            "graphMode": "none",
            "textMode": "auto",
            "justifyMode": "auto",
            "orientation": "auto",
        },
    }


def timeseries(
    title: str,
    targets: list[dict],
    unit: str = "short",
    description: str = "",
    max_value: float | None = None,
) -> dict:
    defaults: dict = {
        "unit": unit,
        "min": 0,
        "custom": {"fillOpacity": 10, "lineWidth": 1, "showPoints": "never"},
        "color": {"mode": "palette-classic"},
    }
    if max_value is not None:
        defaults["max"] = max_value
    return {
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": DS,
        "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def bargauge(title: str, expr: str, legend: str, unit: str, steps: dict) -> dict:
    return {
        "type": "bargauge",
        "title": title,
        "datasource": DS,
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": 0,
                "max": 1,
                "thresholds": steps,
                "color": {"mode": "thresholds"},
            },
            "overrides": [],
        },
        "options": {
            "displayMode": "gradient",
            "orientation": "horizontal",
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showUnfilled": True,
        },
    }


def dashboard(uid: str, title: str, rows: list[list[tuple[dict, int, int]]]) -> dict:
    """Lay out rows of (panel, width, height) on the 24-column grid."""
    panels = []
    y = 0
    pid = 1
    for row in rows:
        x = 0
        height = 0
        for panel, w, h in row:
            panel = dict(panel, id=pid, gridPos={"x": x, "y": y, "w": w, "h": h})
            panels.append(panel)
            pid += 1
            x += w
            height = max(height, h)
        y += height
    return {
        "uid": uid,
        "title": title,
        "tags": ["portfolio"],
        "timezone": "browser",
        "editable": False,
        "graphTooltip": 1,
        "refresh": "1m",
        "time": {"from": "now-24h", "to": "now"},
        "schemaVersion": 41,
        "version": 1,
        "panels": panels,
        "templating": {"list": []},
        "annotations": {"list": []},
        "links": [
            {"title": t, "type": "link", "url": f"/d/{u}"}
            for u, t in (("site-overview", "Site"), ("homelab", "Homelab"), ("backups", "Backups"))
            if u != uid
        ],
    }


UP_DOWN = [
    {
        "type": "value",
        "options": {
            "0": {"text": "Down", "color": "red", "index": 0},
            "1": {"text": "Up", "color": "green", "index": 1},
        },
    }
]
AVAILABILITY = thresholds((None, "red"), (0.99, "orange"), (0.999, "green"))
USAGE = thresholds((None, "green"), (0.7, "orange"), (0.85, "red"))

REQ = "portfolio_http_requests_total"
BUCKET = "portfolio_http_request_duration_seconds_bucket"

site = dashboard(
    "site-overview",
    "Site overview",
    [
        [
            (
                stat(
                    "API availability",
                    'avg_over_time(probe_success{probe="api_health"}[$__range])',
                    unit="percentunit",
                    steps=AVAILABILITY,
                    decimals=2,
                    description="Share of successful /api/health probes from the internet "
                    "in the selected range. Prometheus keeps 7 days.",
                ),
                6,
                4,
            ),
            (
                stat(
                    "Probes now",
                    "probe_success",
                    mappings=UP_DOWN,
                    steps=thresholds((None, "red"), (1, "green")),
                    legend="{{probe}}",
                ),
                6,
                4,
            ),
            (
                stat(
                    "Leads",
                    "sum(increase(portfolio_leads_total[$__range]))",
                    decimals=0,
                    description="Leads stored in the selected range. Count only.",
                ),
                6,
                4,
            ),
            (
                stat(
                    "Contact errors",
                    "sum(increase(portfolio_contact_errors_total[$__range]))",
                    steps=thresholds((None, "green"), (0.5, "red")),
                    decimals=0,
                ),
                6,
                4,
            ),
        ],
        [
            (
                timeseries(
                    "Request rate",
                    [
                        target(
                            f"sum by (route) (rate({REQ}[$__rate_interval]))",
                            "{{route}}",
                        )
                    ],
                    unit="reqps",
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Latency p95",
                    [
                        target(
                            "histogram_quantile(0.95, sum by (le) "
                            f"(rate({BUCKET}[$__rate_interval])))",
                            "p95",
                        ),
                        target(
                            "histogram_quantile(0.5, sum by (le) "
                            f"(rate({BUCKET}[$__rate_interval])))",
                            "p50",
                            ref="B",
                        ),
                    ],
                    unit="s",
                    description="Time to the last response byte at the API. "
                    "Excludes the Cloudflare edge and tunnel.",
                ),
                12,
                8,
            ),
        ],
        [
            (
                timeseries(
                    "Error rate (5xx)",
                    [
                        target(
                            # No 5xx series yet: count it as 0, not as no data.
                            f'(sum(rate({REQ}{{status=~"5.."}}[$__rate_interval])) or vector(0))'
                            f" / sum(rate({REQ}[$__rate_interval]))",
                            "5xx share",
                        )
                    ],
                    unit="percentunit",
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Probe duration",
                    [target("probe_duration_seconds", "{{probe}}")],
                    unit="s",
                    description="Full request time from the obs LXC through the internet.",
                ),
                12,
                8,
            ),
        ],
    ],
)

NODE = 'id=~"node/.+"'
homelab = dashboard(
    "homelab",
    "Homelab",
    [
        [
            (
                stat(
                    "Guests",
                    f'pve_up{{id=~"lxc/.+"}} {WITH_NAME}',
                    mappings=UP_DOWN,
                    steps=thresholds((None, "red"), (1, "green")),
                    legend="{{name}}",
                ),
                12,
                4,
            ),
            (
                stat(
                    "Tunnel connections",
                    "sum by (lxc) (cloudflared_tunnel_ha_connections)",
                    steps=thresholds((None, "red"), (1, "orange"), (2, "green")),
                    legend="{{lxc}}",
                    description="Edge connections per tunnel: `app` for the API, "
                    "`obs` for Grafana.",
                ),
                6,
                4,
            ),
            (
                stat(
                    "Host uptime",
                    f"pve_uptime_seconds{{{NODE}}}",
                    unit="s",
                ),
                6,
                4,
            ),
        ],
        [
            (
                timeseries(
                    "Host CPU",
                    [target(f"pve_cpu_usage_ratio{{{NODE}}}", "host")],
                    unit="percentunit",
                    max_value=1,
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Host RAM",
                    [
                        target(
                            f"pve_memory_usage_bytes{{{NODE}}} / pve_memory_size_bytes{{{NODE}}}",
                            "host",
                        )
                    ],
                    unit="percentunit",
                    max_value=1,
                ),
                12,
                8,
            ),
        ],
        [
            (
                bargauge(
                    "Disk",
                    'pve_disk_usage_bytes{id=~"node/.+|storage/.+"}'
                    ' / pve_disk_size_bytes{id=~"node/.+|storage/.+"}',
                    "{{id}}",
                    "percentunit",
                    USAGE,
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Guest RAM",
                    [target(f'pve_memory_usage_bytes{{id=~"lxc/.+"}} {WITH_NAME}', "{{name}}")],
                    unit="bytes",
                ),
                12,
                8,
            ),
        ],
        [
            (
                timeseries(
                    "Network",
                    [
                        target(
                            f'rate(pve_network_receive_bytes_total{{id=~"lxc/.+"}}'
                            f"[$__rate_interval]) {WITH_NAME}",
                            "{{name}} in",
                        ),
                        target(
                            f'rate(pve_network_transmit_bytes_total{{id=~"lxc/.+"}}'
                            f"[$__rate_interval]) {WITH_NAME}",
                            "{{name}} out",
                            ref="B",
                        ),
                    ],
                    unit="Bps",
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Guest CPU",
                    [target(f'pve_cpu_usage_ratio{{id=~"lxc/.+"}} {WITH_NAME}', "{{name}}")],
                    unit="percentunit",
                    description="Share of the guest's own core limit.",
                ),
                12,
                8,
            ),
        ],
    ],
)

AGE = "max(portfolio:litestream_backup_age_seconds)"
backups = dashboard(
    "backups",
    "Backups",
    [
        [
            (
                stat(
                    "Last upload age",
                    AGE,
                    unit="s",
                    steps=thresholds((None, "green"), (3600, "orange"), (4500, "red")),
                    description="Time since the last Litestream upload to R2. "
                    "Before the first upload after a Litestream start, time since that start.",
                ),
                8,
                4,
            ),
            (
                stat(
                    "Sync errors",
                    "sum(increase(litestream_sync_error_count[$__range]))",
                    steps=thresholds((None, "green"), (0.5, "red")),
                    decimals=0,
                ),
                8,
                4,
            ),
            (
                stat("Database size", "max(litestream_db_size)", unit="bytes"),
                8,
                4,
            ),
        ],
        [
            (
                timeseries(
                    "Upload age",
                    [target(AGE, "age")],
                    unit="s",
                    description="Litestream lag to R2. The BackupStale alert fires above 75 min.",
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "R2 operations",
                    [
                        target(
                            "sum by (operation) "
                            "(increase(litestream_replica_operation_total[$__rate_interval]))",
                            "{{operation}}",
                        )
                    ],
                ),
                12,
                8,
            ),
        ],
        [
            (
                timeseries(
                    "WAL size",
                    [target("max(litestream_wal_size)", "WAL")],
                    unit="bytes",
                ),
                12,
                8,
            ),
            (
                timeseries(
                    "Sync time",
                    [target("rate(litestream_sync_seconds[$__rate_interval])", "sync")],
                    unit="percentunit",
                    description="Share of time Litestream spends syncing the shadow WAL.",
                ),
                12,
                8,
            ),
        ],
    ],
)


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for board in (site, homelab, backups):
        path = OUT / f"{board['uid']}.json"
        text = json.dumps(board, indent=2, ensure_ascii=False) + "\n"
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
    if stale:
        print(f"stale dashboards: {', '.join(stale)}. Run build_dashboards.py and commit.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
