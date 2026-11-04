"""Cloudflare R2 client for the images bucket. Spec section 9.2, plan T16.

R2 speaks the S3 API. This module signs requests with AWS Signature V4 over the
shared `httpx` client, so the API carries no AWS SDK. Only PUT and DELETE of one
object are needed: the public reads go through `IMAGES_BASE_URL`.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

from portfolio_api.config import Settings

REGION = "auto"
SERVICE = "s3"
# Keys are random, so an object never changes. Browsers and the edge cache it for a year.
CACHE_CONTROL = "public, max-age=31536000, immutable"


class R2Error(Exception):
    """An R2 request did not complete. The message names the operation, key, and cause."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_v4(
    *,
    method: str,
    host: str,
    path: str,
    headers: dict[str, str],
    payload_hash: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str,
    now: datetime,
) -> dict[str, str]:
    """Return the headers to send: `headers` plus `x-amz-*` and `Authorization`.

    `path` must already be URI-encoded. Every header passed in is signed.
    The request carries no query string.
    """
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    signed = {k.lower(): v.strip() for k, v in headers.items()}
    signed |= {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    names = sorted(signed)
    canonical_headers = "".join(f"{n}:{signed[n]}\n" for n in names)
    signed_headers = ";".join(names)
    canonical_request = "\n".join(
        [method, path, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, _sha256(canonical_request.encode())]
    )
    key = _hmac(f"AWS4{secret_key}".encode(), day)
    for part in (region, service, "aws4_request"):
        key = _hmac(key, part)
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    out = {n: signed[n] for n in names if n != "host"}
    out["authorization"] = auth
    return out


class R2:
    """PUT and DELETE single objects in the images bucket."""

    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        self._host = f"{settings.r2_account_id.strip()}.r2.cloudflarestorage.com"
        self._bucket = settings.r2_images_bucket.strip()
        self._access_key = settings.r2_access_key_id.strip()
        self._secret_key = settings.r2_secret_access_key.strip()
        self._http = http

    def _path(self, key: str) -> str:
        return f"/{quote(self._bucket, safe='')}/{quote(key, safe='/-_.~')}"

    def _send(self, method: str, key: str, body: bytes, headers: dict[str, str]) -> None:
        path = self._path(key)
        signed = sign_v4(
            method=method,
            host=self._host,
            path=path,
            headers=headers,
            payload_hash=_sha256(body),
            access_key=self._access_key,
            secret_key=self._secret_key,
            region=REGION,
            service=SERVICE,
            now=datetime.now(UTC),
        )
        try:
            res = self._http.request(
                method, f"https://{self._host}{path}", content=body, headers=signed
            )
        except httpx.HTTPError as exc:
            raise R2Error(f"R2 {method} {key}: unreachable: {exc}") from exc
        # S3 DELETE returns 204 for a missing key too, so 404 never reaches here on DELETE.
        if res.is_error:
            raise R2Error(f"R2 {method} {key}: HTTP {res.status_code}: {res.text[:300]}")

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self._send("PUT", key, body, {"content-type": content_type, "cache-control": CACHE_CONTROL})

    def delete(self, key: str) -> None:
        self._send("DELETE", key, b"", {})
