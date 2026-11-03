import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from portfolio_api.config import Settings
from portfolio_api.contact import RESEND_SEND_URL, TURNSTILE_VERIFY_URL, ip_hash
from portfolio_api.main import create_app

SALT = "test-salt-0123456789abcdef0123456789"
VISITOR = "203.0.113.7"
HEADERS = {"CF-Connecting-IP": VISITOR}


@dataclass
class FakeUpstream:
    """Stands in for Turnstile and Resend. Records every request."""

    turnstile_success: bool = True
    turnstile_down: bool = False
    resend_status: int = 200
    turnstile_calls: list[dict[str, list[str]]] = field(default_factory=list)
    emails: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == TURNSTILE_VERIFY_URL:
            if self.turnstile_down:
                raise httpx.ConnectError("down", request=request)
            self.turnstile_calls.append(parse_qs(request.content.decode()))
            body = {"success": self.turnstile_success}
            if not self.turnstile_success:
                body["error-codes"] = ["invalid-input-response"]
            return httpx.Response(200, json=body)
        if url == RESEND_SEND_URL:
            self.emails.append(request)
            return httpx.Response(self.resend_status, json={"id": "email-1"})
        return httpx.Response(404)


def _settings(tmp_path: Path, **overrides: str) -> Settings:
    values = {
        "database_path": tmp_path / "test.db",
        "cors_origin": "https://fatihiazmi.dev",
        "ip_hash_salt": SALT,
        "turnstile_secret": "ts-secret",
        "resend_api_key": "re_test",
        "lead_notify_email": "owner@example.com",
        "lead_from_email": "Site <leads@send.example.com>",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def contact_client(tmp_path: Path, upstream: FakeUpstream) -> Iterator[TestClient]:
    http = httpx.Client(transport=httpx.MockTransport(upstream.handle))
    with TestClient(create_app(_settings(tmp_path), http=http)) as c:
        yield c


@pytest.fixture
def db(contact_client: TestClient) -> sqlite3.Connection:
    return contact_client.app.state.db


def _form(**overrides: object) -> dict[str, object]:
    form: dict[str, object] = {
        "name": "Aisyah Rahman",
        "email": "aisyah@example.com",
        "company": "Acme Sdn Bhd",
        "kind": "freelance",
        "budget": "RM10k–50k",
        "message": "We need a maintenance system for 40 sites.",
        "website": "",
        "turnstile_token": "tok",
    }
    form.update(overrides)
    return form


def _leads(db: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM leads ORDER BY id").fetchall()


def test_valid_lead_is_stored_with_hashed_ip(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    res = contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    [lead] = _leads(db)
    assert lead["name"] == "Aisyah Rahman"
    assert lead["kind"] == "freelance"
    assert lead["budget"] == "RM10k–50k"
    assert lead["status"] == "new"
    assert lead["ip_hash"] == ip_hash(SALT, VISITOR)
    assert VISITOR not in lead["ip_hash"]


def test_turnstile_gets_secret_token_and_ip(
    contact_client: TestClient, upstream: FakeUpstream
) -> None:
    contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert upstream.turnstile_calls == [
        {"secret": ["ts-secret"], "response": ["tok"], "remoteip": [VISITOR]}
    ]


def test_notification_email_sent(contact_client: TestClient, upstream: FakeUpstream) -> None:
    contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    [email] = upstream.emails
    assert email.headers["Authorization"] == "Bearer re_test"
    assert email.headers["Idempotency-Key"] == "lead/1"
    body = json.loads(email.content)
    assert body["to"] == ["owner@example.com"]
    assert body["from"] == "Site <leads@send.example.com>"
    assert body["reply_to"] == "aisyah@example.com"
    assert body["subject"] == "[freelance] New lead from Aisyah Rahman"
    assert "We need a maintenance system for 40 sites." in body["text"]
    assert "Budget: RM10k–50k" in body["text"]


def test_honeypot_returns_ok_and_stores_nothing(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    res = contact_client.post(
        "/api/contact", json=_form(website="http://spam.example"), headers=HEADERS
    )
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert _leads(db) == []
    assert upstream.turnstile_calls == []
    assert upstream.emails == []


def test_rate_limit_allows_five_per_hour_then_429(
    contact_client: TestClient, db: sqlite3.Connection
) -> None:
    for _ in range(5):
        assert contact_client.post("/api/contact", json=_form(), headers=HEADERS).status_code == 200
    res = contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 429
    assert len(_leads(db)) == 5


def test_rate_limit_is_per_ip(contact_client: TestClient) -> None:
    for _ in range(5):
        contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    other = contact_client.post(
        "/api/contact", json=_form(), headers={"CF-Connecting-IP": "198.51.100.9"}
    )
    assert other.status_code == 200


def test_rate_limit_ignores_leads_older_than_an_hour(
    contact_client: TestClient, db: sqlite3.Connection
) -> None:
    for _ in range(5):
        contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    db.execute("UPDATE leads SET created_at = '2026-01-01T00:00:00+00:00'")
    assert contact_client.post("/api/contact", json=_form(), headers=HEADERS).status_code == 200


def test_turnstile_rejected_returns_400(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    upstream.turnstile_success = False
    res = contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 400
    assert _leads(db) == []
    assert upstream.emails == []


def test_turnstile_down_returns_502(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    upstream.turnstile_down = True
    res = contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 502
    assert _leads(db) == []


def test_email_error_keeps_lead(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    upstream.resend_status = 500
    res = contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 200
    assert len(_leads(db)) == 1


def test_budget_dropped_unless_freelance(
    contact_client: TestClient, db: sqlite3.Connection, upstream: FakeUpstream
) -> None:
    contact_client.post("/api/contact", json=_form(kind="hiring"), headers=HEADERS)
    [lead] = _leads(db)
    assert lead["budget"] is None
    assert "Budget: -" in json.loads(upstream.emails[0].content)["text"]


def test_optional_fields_can_be_omitted(contact_client: TestClient, db: sqlite3.Connection) -> None:
    form = _form(kind="other")
    for key in ("company", "budget", "website"):
        del form[key]
    assert contact_client.post("/api/contact", json=form, headers=HEADERS).status_code == 200
    [lead] = _leads(db)
    assert lead["company"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "x" * 101},
        {"email": "not-an-email"},
        {"company": "x" * 151},
        {"kind": "spam"},
        {"budget": "RM1m"},
        {"message": "too short"},
        {"message": "x" * 5001},
        {"turnstile_token": ""},
    ],
)
def test_invalid_fields_return_422(
    contact_client: TestClient,
    db: sqlite3.Connection,
    upstream: FakeUpstream,
    overrides: dict[str, object],
) -> None:
    res = contact_client.post("/api/contact", json=_form(**overrides), headers=HEADERS)
    assert res.status_code == 422
    assert _leads(db) == []
    assert upstream.turnstile_calls == []


def test_unconfigured_contact_returns_503(tmp_path: Path, upstream: FakeUpstream) -> None:
    http = httpx.Client(transport=httpx.MockTransport(upstream.handle))
    app = create_app(_settings(tmp_path, turnstile_secret=""), http=http)
    with TestClient(app) as c:
        res = c.post("/api/contact", json=_form(), headers=HEADERS)
    assert res.status_code == 503
    assert upstream.turnstile_calls == []


def test_no_email_config_still_stores_lead(tmp_path: Path, upstream: FakeUpstream) -> None:
    http = httpx.Client(transport=httpx.MockTransport(upstream.handle))
    app = create_app(_settings(tmp_path, resend_api_key=""), http=http)
    with TestClient(app) as c:
        assert c.post("/api/contact", json=_form(), headers=HEADERS).status_code == 200
        assert len(_leads(c.app.state.db)) == 1
    assert upstream.emails == []


def test_cors_preflight_for_contact(contact_client: TestClient) -> None:
    res = contact_client.options(
        "/api/contact",
        headers={
            "Origin": "https://fatihiazmi.dev",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "https://fatihiazmi.dev"


def test_email_error_logs_resend_reason(
    contact_client: TestClient, upstream: FakeUpstream, caplog: pytest.LogCaptureFixture
) -> None:
    upstream.resend_status = 403
    with caplog.at_level("ERROR", logger="portfolio_api.contact"):
        contact_client.post("/api/contact", json=_form(), headers=HEADERS)
    [record] = [r for r in caplog.records if "notification email failed" in r.getMessage()]
    assert "Resend 403" in record.getMessage()
    assert "email-1" in record.getMessage()


def test_default_sender_is_on_apex_domain() -> None:
    # The Resend domain is the apex. A subdomain sender gets 403.
    assert Settings.model_fields["lead_from_email"].default.endswith("@fatihiazmi.dev>")
