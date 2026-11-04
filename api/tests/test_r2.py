"""R2 client tests. The signer is checked against the AWS S3 SigV4 documentation example."""

import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from portfolio_api.config import Settings
from portfolio_api.r2 import R2, R2Error, sign_v4

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def test_sign_v4_matches_aws_get_object_example() -> None:
    # "Example: GET Object" in the Amazon S3 API reference, "Signature Calculations
    # for the Authorization Header: Transferring Payload in a Single Chunk".
    headers = sign_v4(
        method="GET",
        host="examplebucket.s3.amazonaws.com",
        path="/test.txt",
        headers={"Range": "bytes=0-9"},
        payload_hash=EMPTY_SHA256,
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        region="us-east-1",
        service="s3",
        now=datetime(2013, 5, 24, tzinfo=UTC),
    )
    assert headers["authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
        "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )
    assert headers["x-amz-date"] == "20130524T000000Z"
    assert "host" not in headers


def _r2(handler: httpx.MockTransport) -> R2:
    settings = Settings(
        r2_account_id="acct",
        r2_access_key_id="AKID",
        r2_secret_access_key="secret",
        r2_images_bucket="images",
    )
    return R2(settings, httpx.Client(transport=handler))


def test_put_sends_signed_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    _r2(httpx.MockTransport(handler)).put("sims/ab.png", b"data", "image/png")
    (req,) = seen
    assert req.method == "PUT"
    assert str(req.url) == "https://acct.r2.cloudflarestorage.com/images/sims/ab.png"
    assert req.content == b"data"
    assert req.headers["content-type"] == "image/png"
    assert req.headers["x-amz-content-sha256"] == hashlib.sha256(b"data").hexdigest()
    auth = req.headers["authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKID/")
    assert "/auto/s3/aws4_request" in auth
    assert "SignedHeaders=cache-control;content-type;host;x-amz-content-sha256;x-amz-date" in auth


def test_delete_sends_empty_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    _r2(httpx.MockTransport(handler)).delete("sims/ab.png")
    assert seen[0].method == "DELETE"
    assert seen[0].headers["x-amz-content-sha256"] == EMPTY_SHA256


def test_http_error_raises() -> None:
    r2 = _r2(httpx.MockTransport(lambda _: httpx.Response(403, text="<Error>denied</Error>")))
    with pytest.raises(R2Error, match="PUT sims/ab.png: HTTP 403"):
        r2.put("sims/ab.png", b"x", "image/png")


def test_unreachable_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(R2Error, match="unreachable"):
        _r2(httpx.MockTransport(handler)).delete("k")
