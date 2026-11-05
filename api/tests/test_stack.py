"""`GET /api/stack` and the admin `last_backup_at`. Spec section 7, plan T22.

A fake Prometheus behind `httpx.MockTransport` answers each allowlisted query.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from portfolio_api import stack
from portfolio_api.config import Settings
from portfolio_api.main import create_app
from portfolio_api.prometheus import Prometheus, PrometheusDown

PROM = "http://prom.test:9090"
NOW = 1_800_000_123
# Labels a real Prometheus attaches. None of them may reach the response.
LABELS = {"instance": "192.168.0.151:9464", "job": "api", "lxc": "app", "id": "node/nik"}


def _vector(value: str | None) -> dict[str, Any]:
    result = [] if value is None else [{"metric": LABELS, "value": [NOW, value]}]
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def _matrix(values: list[tuple[int, str]]) -> dict[str, Any]:
    result = [{"metric": LABELS, "values": [[t, v] for t, v in values]}] if values else []
    return {"status": "success", "data": {"resultType": "matrix", "result": result}}


class FakeProm:
    """Instant answers by query name. Range answers: two points per query."""

    def __init__(self) -> None:
        self.instant: dict[str, str | None] = {
            "probe_up": "1",
            "availability": "0.99462",
            "tunnel_connections": "4",
            "backup_lag": "0",
            "last_upload": "1799990000",
            "cpu": "0.034215",
            "memory": "0.71",
            "disk": "0.4321",
        }
        self.down = False
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "prom.test"
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        q = request.url.params["query"]
        self.calls.append(q)
        if request.url.path == "/api/v1/query":
            name = next(n for n, expr in stack.INSTANT.items() if expr == q)
            return httpx.Response(200, json=_vector(self.instant[name]))
        assert request.url.path == "/api/v1/query_range"
        assert q in stack.RANGE.values()
        start = int(request.url.params["start"])
        step = int(request.url.params["step"])
        # A point at the start, a gap, then NaN at the third point.
        return httpx.Response(200, json=_matrix([(start, "1.23456"), (start + 2 * step, "NaN")]))


@pytest.fixture
def prom() -> FakeProm:
    return FakeProm()


def _settings(tmp_path: Path, **kw: Any) -> Settings:
    return Settings(database_path=tmp_path / "test.db", cors_origin="https://fatihiazmi.dev", **kw)


@pytest.fixture
def api(tmp_path: Path, prom: FakeProm) -> Iterator[TestClient]:
    http = httpx.Client(transport=httpx.MockTransport(prom))
    with TestClient(create_app(_settings(tmp_path, prometheus_url=PROM), http=http)) as c:
        c.app.state.stack_cache = stack.StackCache(clock=lambda: NOW)
        yield c


def test_stack_returns_numbers(api: TestClient) -> None:
    r = api.get("/api/stack")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["generated_at"] == "2027-01-15T08:02:03+00:00"
    assert body["api_probe_up"] is True
    assert body["availability"] == {"ratio": 0.9946, "window_days": 7}
    assert body["tunnel_connections"] == 4
    assert body["backup"] == {"lag_seconds": 0, "last_upload_at": "2027-01-15T05:13:20+00:00"}
    assert body["host"] == {"cpu": 0.0342, "memory": 0.71, "disk": 0.4321}
    assert body["leads_total"] == 0


def test_stack_series_fixed_length_with_gaps(api: TestClient) -> None:
    series = api.get("/api/stack").json()["series"]
    end = NOW // 600 * 600
    assert series["start"] == end - 86_400
    assert series["step_seconds"] == 600
    for name in stack.RANGE:
        values = series[name]
        assert len(values) == 145
        assert values[1] is None  # gap
        assert values[2] is None  # NaN
        assert values[3:] == [None] * 142
    assert series["requests_per_hour"][0] == 1.23
    assert series["latency_p95_ms"][0] == 1.2
    assert series["cpu"][0] == 1.2346


def test_stack_sends_no_labels(api: TestClient) -> None:
    """Spec 7: no host names, no internal IPs, no labels that name hosts."""
    r = api.get("/api/stack")
    for value in ["192.168", "node/nik", '"lxc"', '"instance"', '"job"', '"id"']:
        assert value not in r.text

    def strings(x: Any) -> Iterator[str]:
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from strings(v)
        elif isinstance(x, list):
            for v in x:
                yield from strings(v)
        elif isinstance(x, str):
            yield x

    assert set(strings(r.json())).isdisjoint(LABELS.values())


def test_stack_runs_only_the_allowlist(api: TestClient, prom: FakeProm) -> None:
    api.get("/api/stack?query=up")
    assert sorted(prom.calls) == sorted([*stack.INSTANT.values(), *stack.RANGE.values()])


def test_stack_counts_leads_from_sqlite(api: TestClient) -> None:
    db = api.app.state.db
    for _ in range(3):
        db.execute(
            "INSERT INTO leads (created_at, name, email, kind, message, ip_hash)"
            " VALUES ('2026-11-05T00:00:00Z', 'a', 'a@b.c', 'other', 'hello there', 'x')"
        )
    assert api.get("/api/stack").json()["leads_total"] == 3


def test_stack_absent_series_are_null(api: TestClient, prom: FakeProm) -> None:
    prom.instant = dict.fromkeys(prom.instant)
    body = api.get("/api/stack").json()
    assert body["api_probe_up"] is None
    assert body["availability"]["ratio"] is None
    assert body["tunnel_connections"] is None
    assert body["backup"] == {"lag_seconds": None, "last_upload_at": None}
    assert body["host"] == {"cpu": None, "memory": None, "disk": None}


def test_stack_probe_down(api: TestClient, prom: FakeProm) -> None:
    prom.instant["probe_up"] = "0"
    assert api.get("/api/stack").json()["api_probe_up"] is False


def test_stack_caches_for_30_seconds(api: TestClient, prom: FakeProm) -> None:
    clock = [float(NOW)]
    api.app.state.stack_cache = stack.StackCache(clock=lambda: clock[0])
    queries = len(stack.INSTANT) + len(stack.RANGE)
    api.get("/api/stack")
    api.get("/api/stack")
    assert len(prom.calls) == queries
    clock[0] += 30
    api.get("/api/stack")
    assert len(prom.calls) == 2 * queries


def test_stack_prometheus_down_is_503_and_cached(api: TestClient, prom: FakeProm) -> None:
    prom.down = True
    r = api.get("/api/stack")
    assert r.status_code == 503
    assert r.json() == {"detail": "metrics offline"}
    prom.down = False
    assert api.get("/api/stack").status_code == 503
    assert prom.calls == []


def test_stack_off_without_prometheus_url(client: TestClient) -> None:
    r = client.get("/api/stack")
    assert r.status_code == 503
    assert r.json() == {"detail": "metrics off"}


def test_stack_cors_allows_the_site(api: TestClient) -> None:
    r = api.get("/api/stack", headers={"Origin": "https://fatihiazmi.dev"})
    assert r.headers["access-control-allow-origin"] == "https://fatihiazmi.dev"


# --- Prometheus client ---


def _client(handler: Any) -> Prometheus:
    return Prometheus(PROM + "/", httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_5xx_is_down() -> None:
    p = _client(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(PrometheusDown, match="HTTP 503"):
        p.instant("up")


def test_client_bad_query_is_none(caplog: pytest.LogCaptureFixture) -> None:
    body = {"status": "error", "errorType": "bad_data", "error": "parse error"}
    p = _client(lambda r: httpx.Response(400, json=body))
    assert p.instant("up{") is None
    assert "parse error" in caplog.text


def test_client_many_series_is_none(caplog: pytest.LogCaptureFixture) -> None:
    body = _vector("1")
    body["data"]["result"] *= 2
    p = _client(lambda r: httpx.Response(200, json=body))
    assert p.instant("up") is None
    assert "2 series" in caplog.text


def test_client_infinity_is_none() -> None:
    p = _client(lambda r: httpx.Response(200, json=_vector("+Inf")))
    assert p.instant("x") is None


# --- Admin summary ---


def test_summary_last_backup_at(api: TestClient) -> None:
    api.app.state.access = _StubAccess()
    r = api.get("/api/admin/summary", headers={"Cf-Access-Jwt-Assertion": "t"})
    assert r.status_code == 200, r.text
    assert r.json()["last_backup_at"] == "2027-01-15T05:13:20+00:00"


def test_summary_last_backup_at_prometheus_down(api: TestClient, prom: FakeProm) -> None:
    prom.down = True
    api.app.state.access = _StubAccess()
    r = api.get("/api/admin/summary", headers={"Cf-Access-Jwt-Assertion": "t"})
    assert r.status_code == 200
    assert r.json()["last_backup_at"] is None


class _StubAccess:
    def verify(self, token: str) -> str:
        return "owner@test"
