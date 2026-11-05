"""Read-only Prometheus HTTP API client. Spec section 7, plan T22.

Callers pass fixed PromQL strings only. Every query must aggregate to one series:
the client reads values and drops all labels, so no host name or IP leaves it.

Errors:
- Network error, timeout, or a 5xx: `PrometheusDown`. Prometheus or the `obs` LXC is down.
- A 4xx or an error body: logged, the value is `None`. That is a bad query in this repo.
"""

import logging
import math
from typing import Any

import httpx

log = logging.getLogger("portfolio_api.prometheus")

# Per request. The API and Prometheus share the LAN, so a healthy answer takes milliseconds.
TIMEOUT = httpx.Timeout(3.0)


class PrometheusDown(Exception):
    """Prometheus did not answer, or answered with a 5xx."""


def _number(raw: str) -> float | None:
    """Prometheus sends sample values as strings. NaN and infinity become `None`."""
    value = float(raw)
    return value if math.isfinite(value) else None


class Prometheus:
    def __init__(self, base_url: str, http: httpx.Client) -> None:
        self._base = base_url.rstrip("/")
        self._http = http

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]] | None:
        try:
            r = self._http.get(f"{self._base}{path}", params=params, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise PrometheusDown(f"{type(e).__name__}: {e}") from e
        if r.status_code >= 500:
            raise PrometheusDown(f"HTTP {r.status_code}")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or body.get("status") != "success":
            log.error("prometheus query %r: HTTP %s %s", params["query"], r.status_code, body)
            return None
        result = body["data"]["result"]
        if len(result) > 1:
            log.error("prometheus query %r: %d series, expected 1", params["query"], len(result))
            return None
        return result

    def instant(self, query: str) -> float | None:
        """Value of a one-series instant query. `None` when the series is absent."""
        result = self._get("/api/v1/query", {"query": query})
        return _number(result[0]["value"][1]) if result else None

    def range(self, query: str, start: int, end: int, step: int) -> list[float | None]:
        """Values of a one-series range query at `start, start + step, ..., end`.

        Gaps in the data come back as `None`, so the list length is always fixed.
        """
        points: list[float | None] = [None] * ((end - start) // step + 1)
        result = self._get(
            "/api/v1/query_range", {"query": query, "start": start, "end": end, "step": step}
        )
        for ts, raw in result[0]["values"] if result else []:
            i = (round(float(ts)) - start) // step
            if 0 <= i < len(points):
                points[i] = _number(raw)
        return points
