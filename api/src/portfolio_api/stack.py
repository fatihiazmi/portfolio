"""`GET /api/stack`: live numbers for the public `/stack` page. Spec section 7, plan T22.

FastAPI asks Prometheus a fixed allowlist of PromQL queries. Visitors never send a query,
and the route takes no parameters. Every query aggregates to one series, and the response
holds numbers and time series only: no labels, host names, or IPs.

Cache: one response for `CACHE_SECONDS`, shared by every visitor. Browsers get `no-store`.
A Prometheus error is cached for the same time, so an outage costs one 3 s timeout per window,
not one per visitor.

Errors:
- `PROMETHEUS_URL` unset: 503.
- Prometheus unreachable, timeout, or a 5xx: 503. The page shows "metrics offline".

The 30-day availability in spec 7 needs 30 days of data. Prometheus keeps 7 on the 4 GB host
(spec 7a.1), so the window is 7 days and the response names it.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from portfolio_api.prometheus import Prometheus, PrometheusDown

log = logging.getLogger("portfolio_api.stack")

router = APIRouter(prefix="/api", tags=["stack"])

CACHE_SECONDS = 30
# Prometheus retention. Spec 7a.1: 7 days now, 15 after the RAM upgrade.
WINDOW_DAYS = 7
# 24 h charts: one point per 10 min, 145 points.
SERIES_HOURS = 24
STEP_SECONDS = 600

_NODE = 'id=~"node/.+"'
# The rate window equals the step, so each point covers the 10 min before it.
_REQ_RATE = 'rate(portfolio_http_requests_total{route!="/api/health"}[10m])'
_LATENCY_RATE = "rate(portfolio_http_request_duration_seconds_bucket[10m])"

# Instant queries. Name -> PromQL. Each wraps in an aggregation, so the result is one series.
INSTANT = {
    "probe_up": 'min(probe_success{probe="api_health"})',
    "availability": f'min(avg_over_time(probe_success{{probe="api_health"}}[{WINDOW_DAYS}d]))',
    # The public tunnel only. The `obs` tunnel carries Grafana.
    "tunnel_connections": 'sum(cloudflared_tunnel_ha_connections{job="cloudflared"})',
    "backup_lag": "max(portfolio:litestream_backup_lag_seconds)",
    "last_upload": (
        f"max(max_over_time(portfolio:litestream_last_upload_timestamp_seconds[{WINDOW_DAYS}d]))"
    ),
    "cpu": f"max(pve_cpu_usage_ratio{{{_NODE}}})",
    "memory": f"max(pve_memory_usage_bytes{{{_NODE}}} / pve_memory_size_bytes{{{_NODE}}})",
    "disk": f"max(pve_disk_usage_bytes{{{_NODE}}} / pve_disk_size_bytes{{{_NODE}}})",
}

# Range queries for the 24 h charts. Health checks hit `/api/health` 3 times a minute:
# the blackbox probe once, the Docker healthcheck twice. The request rate leaves them out.
# Latency keeps them, so the chart has data when no visitor is on the site.
RANGE = {
    "requests_per_hour": f"sum({_REQ_RATE}) * 3600",
    "latency_p95_ms": f"histogram_quantile(0.95, sum by (le) ({_LATENCY_RATE})) * 1000",
    "cpu": INSTANT["cpu"],
    "memory": INSTANT["memory"],
    "disk": INSTANT["disk"],
}

# Decimal places per value, so the JSON stays small.
_RATIO = 4
_MS = 1
_RATE = 2


class Availability(BaseModel):
    # Share of successful `/api/health` probes from the internet, 0 to 1.
    ratio: float | None
    window_days: int


class Backup(BaseModel):
    # Seconds the newest database change has waited for its upload to R2. 0: in sync.
    lag_seconds: float | None
    # Time of the last upload to R2 in the window. Null: no upload in `WINDOW_DAYS` days.
    last_upload_at: str | None


class Host(BaseModel):
    # Proxmox host use, 0 to 1.
    cpu: float | None
    memory: float | None
    disk: float | None


class Series(BaseModel):
    # Unix time of the first point. Point `i` is at `start + i * step_seconds`.
    start: int
    step_seconds: int
    # Each list has one value per point. Null: no data at that point.
    requests_per_hour: list[float | None]
    latency_p95_ms: list[float | None]
    cpu: list[float | None]
    memory: list[float | None]
    disk: list[float | None]


class Stack(BaseModel):
    generated_at: str
    # Last blackbox probe of `/api/health` from the internet. Null: no probe data.
    api_probe_up: bool | None
    availability: Availability
    # Open connections from `cloudflared` to the Cloudflare edge. Healthy: 4.
    tunnel_connections: int | None
    backup: Backup
    host: Host
    # Leads stored in SQLite. A count only, never content.
    leads_total: int
    series: Series


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _round(value: float | None, places: int) -> float | None:
    return None if value is None else round(value, places)


def build(prom: Prometheus, conn: sqlite3.Connection, now: float) -> Stack:
    """Run every allowlisted query once. Raises `PrometheusDown`."""
    v = {name: prom.instant(q) for name, q in INSTANT.items()}

    end = int(now) // STEP_SECONDS * STEP_SECONDS
    start = end - SERIES_HOURS * 3600
    places = {"requests_per_hour": _RATE, "latency_p95_ms": _MS}
    series = {
        name: [_round(x, places.get(name, _RATIO)) for x in prom.range(q, start, end, STEP_SECONDS)]
        for name, q in RANGE.items()
    }

    leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    probe = v["probe_up"]
    tunnel = v["tunnel_connections"]
    upload = v["last_upload"]
    return Stack(
        generated_at=_iso(now),
        api_probe_up=None if probe is None else probe >= 1,
        availability=Availability(ratio=_round(v["availability"], _RATIO), window_days=WINDOW_DAYS),
        tunnel_connections=None if tunnel is None else int(tunnel),
        backup=Backup(
            lag_seconds=_round(v["backup_lag"], 0),
            last_upload_at=None if upload is None else _iso(upload),
        ),
        host=Host(
            cpu=_round(v["cpu"], _RATIO),
            memory=_round(v["memory"], _RATIO),
            disk=_round(v["disk"], _RATIO),
        ),
        leads_total=leads,
        series=Series(start=start, step_seconds=STEP_SECONDS, **series),
    )


class StackCache:
    """One shared result for `CACHE_SECONDS`. The lock stops parallel visitors from
    each running the queries when the entry expires."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._expires = 0.0
        self._value: Stack | None = None

    def get(self, fill: Callable[[float], Stack]) -> Stack | None:
        """Cached `Stack`, or `None` while Prometheus is down."""
        with self._lock:
            now = self._clock()
            if now >= self._expires:
                try:
                    self._value = fill(now)
                except PrometheusDown as e:
                    log.warning("stack: prometheus down: %s", e)
                    self._value = None
                self._expires = now + CACHE_SECONDS
            return self._value


@router.get("/stack", response_model=Stack)
def stack(request: Request, response: Response) -> Stack:
    """Live metrics for `/stack`. 503 when Prometheus is off or down."""
    prom: Prometheus | None = request.app.state.prometheus
    if prom is None:
        raise HTTPException(503, "metrics off")
    conn: sqlite3.Connection = request.app.state.db
    result = request.app.state.stack_cache.get(lambda now: build(prom, conn, now))
    if result is None:
        raise HTTPException(503, "metrics offline")
    # The server cache above serves every visitor. A browser cache would hide an outage.
    response.headers["Cache-Control"] = "no-store"
    return result
