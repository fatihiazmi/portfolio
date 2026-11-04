"""Admin gate tests. Plan T14: missing JWT, bad JWT, and a write without the header."""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from portfolio_api.config import Settings
from portfolio_api.main import create_app

TEAM = "team.cloudflareaccess.com"
AUD = "aud-tag-123"
EMAIL = "owner@example.com"
KID = "key-1"
CERTS_URL = f"https://{TEAM}/cdn-cgi/access/certs"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(*pairs: tuple[str, rsa.RSAPrivateKey]) -> dict[str, Any]:
    keys = []
    for kid, key in pairs:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        keys.append({**jwk, "kid": kid, "alg": "RS256", "use": "sig"})
    # Cloudflare's certs body also carries PEM certs next to `keys`.
    return {"keys": keys, "public_cert": {"kid": kid, "cert": "unused"}}


def token(
    *,
    key: rsa.RSAPrivateKey = KEY,
    kid: str = KID,
    aud: str = AUD,
    iss: str = f"https://{TEAM}",
    email: str = EMAIL,
    exp_in: int = 600,
) -> str:
    now = int(time.time())
    claims = {"aud": [aud], "iss": iss, "email": email, "iat": now, "exp": now + exp_in}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class Certs:
    """Mock Access certs endpoint. Counts fetches."""

    def __init__(self) -> None:
        self.body: dict[str, Any] = jwks((KID, KEY))
        self.status = 200
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == CERTS_URL
        self.calls += 1
        return httpx.Response(self.status, json=self.body)


@pytest.fixture
def certs() -> Certs:
    return Certs()


@pytest.fixture
def admin(tmp_path: Path, certs: Certs) -> Iterator[TestClient]:
    settings = Settings(
        database_path=tmp_path / "a.db",
        cf_access_team_domain=TEAM,
        cf_access_aud=AUD,
        admin_email=EMAIL,
    )
    http = httpx.Client(transport=httpx.MockTransport(certs))
    with TestClient(create_app(settings, http=http)) as c:
        yield c


def auth(t: str, **extra: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": t, **extra}


# --- Config ---


@pytest.mark.parametrize("path", ["/api/admin/me", "/admin", "/admin/projects"])
def test_unconfigured_admin_fails_closed(client: TestClient, path: str) -> None:
    res = client.get(path, headers=auth(token()))
    assert res.status_code == 503


def test_public_paths_skip_the_gate(admin: TestClient, certs: Certs) -> None:
    assert admin.get("/api/health").status_code == 200
    assert admin.get("/api/projects").status_code == 200
    assert admin.get("/administrator").status_code == 404
    assert certs.calls == 0


# --- Missing JWT ---


@pytest.mark.parametrize("path", ["/api/admin/me", "/admin", "/admin/index.html"])
def test_missing_jwt_is_403(admin: TestClient, path: str) -> None:
    assert admin.get(path).status_code == 403


def test_missing_jwt_write_is_403(admin: TestClient) -> None:
    res = admin.post("/api/admin/me", headers={"X-Requested-With": "admin"})
    assert res.status_code == 403


# --- Bad JWT ---


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("not-a-jwt", id="garbage"),
        pytest.param(token(key=OTHER_KEY), id="wrong-signature"),
        pytest.param(token(aud="other-app"), id="wrong-aud"),
        pytest.param(token(iss="https://evil.cloudflareaccess.com"), id="wrong-iss"),
        pytest.param(token(exp_in=-120), id="expired"),
        pytest.param(token(email="someone@example.com"), id="wrong-email"),
        pytest.param(token(kid="unknown"), id="unknown-kid"),
        pytest.param(
            jwt.encode(
                {"aud": AUD, "email": EMAIL}, "s" * 32, algorithm="HS256", headers={"kid": KID}
            ),
            id="hs256",
        ),
        pytest.param(
            jwt.encode({"aud": AUD, "email": EMAIL}, None, algorithm="none", headers={"kid": KID}),
            id="alg-none",
        ),
    ],
)
def test_bad_jwt_is_403(admin: TestClient, bad: str) -> None:
    res = admin.get("/api/admin/me", headers=auth(bad))
    assert res.status_code == 403
    assert res.json() == {"detail": "Admin login required."}


def test_certs_fetch_error_is_403(admin: TestClient, certs: Certs) -> None:
    certs.status = 500
    assert admin.get("/api/admin/me", headers=auth(token())).status_code == 403


# --- Valid JWT ---


def test_valid_jwt_reaches_the_route(admin: TestClient) -> None:
    res = admin.get("/api/admin/me", headers=auth(token()))
    assert res.status_code == 200
    assert res.json() == {"email": EMAIL}


def test_email_match_ignores_case(admin: TestClient) -> None:
    res = admin.get("/api/admin/me", headers=auth(token(email="Owner@Example.com")))
    assert res.status_code == 200


def test_keys_are_cached(admin: TestClient, certs: Certs) -> None:
    for _ in range(3):
        assert admin.get("/api/admin/me", headers=auth(token())).status_code == 200
    assert certs.calls == 1


def test_rotated_key_is_fetched(
    admin: TestClient, certs: Certs, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert admin.get("/api/admin/me", headers=auth(token())).status_code == 200
    certs.body = jwks((KID, KEY), ("key-2", OTHER_KEY))
    # An unknown kid refetches only after KEYS_MIN_REFRESH seconds.
    monkeypatch.setattr("portfolio_api.admin_auth.KEYS_MIN_REFRESH", 0)
    res = admin.get("/api/admin/me", headers=auth(token(key=OTHER_KEY, kid="key-2")))
    assert res.status_code == 200
    assert certs.calls == 2


# --- Writes ---


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_without_header_is_403(admin: TestClient, method: str) -> None:
    res = admin.request(method, "/api/admin/me", headers=auth(token()))
    assert res.status_code == 403
    assert res.json() == {"detail": "Missing X-Requested-With: admin header."}


def test_write_with_wrong_header_value_is_403(admin: TestClient) -> None:
    res = admin.post(
        "/api/admin/me", headers=auth(token(), **{"X-Requested-With": "XMLHttpRequest"})
    )
    assert res.status_code == 403


def test_write_with_header_passes_the_gate(admin: TestClient) -> None:
    # `/me` is GET only, so a request past the gate gets 405 from routing.
    res = admin.post("/api/admin/me", headers=auth(token(), **{"X-Requested-With": "admin"}))
    assert res.status_code == 405
