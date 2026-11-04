"""Admin gate. Spec section 9.2, plan T14.

Cloudflare Access gates `/admin*` and `/api/admin*` at the edge. This middleware checks
every such request again, so a request that reaches the app around Access still fails:

1. Admin config missing: 503. The gate fails closed.
2. No `Cf-Access-Jwt-Assertion` header: 403.
3. JWT signature, `aud`, `iss`, or `exp` wrong: 403. Keys come from the team's certs URL.
4. JWT `email` is not `ADMIN_EMAIL`: 403.
5. A write (POST, PUT, PATCH, DELETE) without `X-Requested-With: admin`: 403.
   A cross-site form or `fetch` cannot set that header without a CORS preflight,
   and CORS never allows it. This blocks CSRF that rides the Access cookie.

Passing requests carry the admin email in `request.state.admin_email`.
"""

import logging
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from portfolio_api.config import Settings

log = logging.getLogger("portfolio_api.admin_auth")

JWT_HEADER = "Cf-Access-Jwt-Assertion"
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
PREFIXES = ("/admin", "/api/admin")
# Seconds of clock skew allowed on `exp`, `nbf`, and `iat`.
LEEWAY = 30
# Keys are refetched after this many seconds, or on an unknown `kid` at most this often.
KEYS_TTL = 3600
KEYS_MIN_REFRESH = 60


class AccessDenied(Exception):
    """The request carries no valid Access JWT for the admin."""


def is_admin_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in PREFIXES)


class AccessVerifier:
    """Checks Access JWTs against the team's public keys. Thread-safe. One per app."""

    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        team = settings.cf_access_team_domain.strip().removeprefix("https://").rstrip("/")
        self._issuer = f"https://{team}"
        self._certs_url = f"{self._issuer}/cdn-cgi/access/certs"
        self._audience = settings.cf_access_aud.strip()
        self._email = settings.admin_email.strip().lower()
        self._http = http
        self._lock = threading.Lock()
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0

    def verify(self, token: str) -> str:
        """Return the admin email from a valid token. Raise `AccessDenied` otherwise."""
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise AccessDenied(f"malformed token: {exc}") from exc
        if not isinstance(kid, str):
            raise AccessDenied("token header has no kid")
        key = self._key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=LEEWAY,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise AccessDenied(f"invalid token: {exc}") from exc
        email = str(claims.get("email", "")).strip().lower()
        if email != self._email:
            raise AccessDenied("token email is not the admin email")
        return email

    def _key(self, kid: str) -> jwt.PyJWK:
        with self._lock:
            age = time.monotonic() - self._fetched_at
            stale = age > KEYS_TTL
            unknown = kid not in self._keys and age > KEYS_MIN_REFRESH
            if stale or unknown:
                self._refresh()
            key = self._keys.get(kid)
        if key is None:
            raise AccessDenied("token kid is not in the team keys")
        return key

    def _refresh(self) -> None:
        try:
            res = self._http.get(self._certs_url)
            res.raise_for_status()
            keyset = jwt.PyJWKSet.from_dict(res.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            # Keep the old keys. A fetch error never grants access.
            log.warning("Access certs fetch from %s failed: %s", self._certs_url, exc)
            self._fetched_at = time.monotonic()
            return
        self._keys = {k.key_id: k for k in keyset.keys if k.key_id}
        self._fetched_at = time.monotonic()


def _deny(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


async def admin_gate(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """HTTP middleware. Non-admin paths pass through untouched."""
    if not is_admin_path(request.url.path):
        return await call_next(request)

    verifier: AccessVerifier | None = getattr(request.app.state, "access", None)
    if verifier is None:
        return _deny(503, "Admin is not configured.")

    token = request.headers.get(JWT_HEADER)
    if not token:
        return _deny(403, "Admin login required.")
    try:
        email = await run_in_threadpool(verifier.verify, token)
    except AccessDenied as exc:
        log.info("admin denied: %s %s: %s", request.method, request.url.path, exc)
        return _deny(403, "Admin login required.")

    if request.method in WRITE_METHODS and request.headers.get("X-Requested-With") != "admin":
        log.info("admin write without X-Requested-With: %s %s", request.method, request.url.path)
        return _deny(403, "Missing X-Requested-With: admin header.")

    request.state.admin_email = email
    return await call_next(request)
