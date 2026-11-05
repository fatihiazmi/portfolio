import socket
import urllib.request
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY, generate_latest

from portfolio_api.config import Settings
from portfolio_api.contact import TURNSTILE_VERIFY_URL
from portfolio_api.main import create_app

ERRORS = "portfolio_contact_errors_total"


def _value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_requests_counted_by_route_template(client: TestClient) -> None:
    labels = {"method": "GET", "route": "/api/projects/{slug}", "status": "404"}
    before = _value("portfolio_http_requests_total", **labels)
    client.get("/api/projects/no-such-slug")
    client.get("/api/projects/other-slug")
    assert _value("portfolio_http_requests_total", **labels) == before + 2


def test_unmatched_path_never_becomes_a_label(client: TestClient) -> None:
    before = _value("portfolio_http_requests_total", method="GET", route="other", status="404")
    client.get("/wp-login.php")
    after = _value("portfolio_http_requests_total", method="GET", route="other", status="404")
    assert after == before + 1
    assert "wp-login" not in _exposition()


def test_latency_observed(client: TestClient) -> None:
    labels = {"method": "GET", "route": "/api/health"}
    before = _value("portfolio_http_request_duration_seconds_count", **labels)
    client.get("/api/health")
    assert _value("portfolio_http_request_duration_seconds_count", **labels) == before + 1


def test_contact_errors_start_at_zero(client: TestClient) -> None:
    for reason in ("not_configured", "turnstile_unavailable", "email_failed"):
        sample = REGISTRY.get_sample_value("portfolio_contact_errors_total", {"reason": reason})
        assert sample is not None


def test_contact_not_configured_counts_error(client: TestClient) -> None:
    before = _value("portfolio_contact_errors_total", reason="not_configured")
    res = client.post("/api/contact", json={})
    # Validation runs first. A valid body reaches the config check.
    assert res.status_code == 422
    client.post(
        "/api/contact",
        json={
            "name": "A",
            "email": "a@example.com",
            "kind": "other",
            "message": "x" * 20,
            "turnstile_token": "t",
        },
    )
    assert _value("portfolio_contact_errors_total", reason="not_configured") == before + 1


def test_lead_and_turnstile_error_counted(tmp_path: Path) -> None:
    down = False

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TURNSTILE_VERIFY_URL:
            if down:
                raise httpx.ConnectError("down", request=request)
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    settings = Settings(
        database_path=tmp_path / "test.db",
        ip_hash_salt="salt-0123456789abcdef",
        turnstile_secret="ts",
    )
    form = {
        "name": "A",
        "email": "a@example.com",
        "kind": "other",
        "message": "x" * 20,
        "turnstile_token": "t",
    }
    http = httpx.Client(transport=httpx.MockTransport(handle))
    with TestClient(create_app(settings, http=http)) as c:
        leads = _value("portfolio_leads_total")
        errors = _value(ERRORS, reason="turnstile_unavailable")
        assert c.post("/api/contact", json=form).status_code == 200
        assert _value("portfolio_leads_total") == leads + 1
        down = True
        assert c.post("/api/contact", json=form).status_code == 502
        assert _value(ERRORS, reason="turnstile_unavailable") == errors + 1
        assert _value("portfolio_leads_total") == leads + 1


def test_metrics_not_on_api_port(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 404


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _exposition(port: int | None = None) -> str:
    if port is None:
        return generate_latest(REGISTRY).decode()
    url = f"http://127.0.0.1:{port}/metrics"
    with urllib.request.urlopen(url, timeout=2) as res:  # noqa: S310 - fixed local URL
        return res.read().decode()


def test_metrics_server_on_own_port(tmp_path: Path) -> None:
    port = _free_port()
    settings = Settings(
        database_path=tmp_path / "test.db", metrics_host="127.0.0.1", metrics_port=port
    )
    with TestClient(create_app(settings)) as c:
        c.get("/api/health")
        body = _exposition(port)
        assert "portfolio_http_requests_total" in body
        assert "portfolio_leads_total" in body
    # The server stops with the app.
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", port)) != 0
