"""Upload checks: type from bytes, size cap, SVG sanitising. Spec section 11."""

from pathlib import Path

import pytest

from portfolio_api.uploads import MAX_BYTES, UploadRejected, check_image, sanitize_svg

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 32
DEMO = Path(__file__).parent.parent / "demo" / "template-demo"


def svg(body: str, root_attrs: str = "") -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
        f' viewBox="0 0 10 10"{root_attrs}>{body}</svg>'
    ).encode()


@pytest.mark.parametrize(
    ("data", "content_type", "ext"),
    [(PNG, "image/png", "png"), (JPEG, "image/jpeg", "jpg"), (WEBP, "image/webp", "webp")],
)
def test_raster_types_pass_unchanged(data: bytes, content_type: str, ext: str) -> None:
    out = check_image(data)
    assert (out.body, out.content_type, out.ext) == (data, content_type, ext)


def test_type_comes_from_bytes() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(b"GIF89a" + b"\x00" * 20)
    assert exc.value.status == 415


def test_over_5_mb_is_413() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(PNG + b"\x00" * MAX_BYTES)
    assert exc.value.status == 413


def test_empty_is_422() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(b"")
    assert exc.value.status == 422


def test_svg_only_rejects_raster() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(PNG, svg_only=True)
    assert exc.value.status == 415


def test_svg_without_namespace_is_415() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(b'<svg viewBox="0 0 1 1"><rect/></svg>')
    assert exc.value.status == 415


def test_html_is_415() -> None:
    with pytest.raises(UploadRejected) as exc:
        check_image(b"<html><script>alert(1)</script></html>")
    assert exc.value.status == 415


def test_svg_dtd_is_rejected() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&b;</text></svg>'
    )
    with pytest.raises(UploadRejected) as exc:
        check_image(bomb)
    assert exc.value.status == 415


def test_svg_keeps_drawing() -> None:
    out = sanitize_svg(
        svg(
            '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient>'
            "<style>.a{fill:url(#g)}</style></defs>"
            '<g class="a"><rect width="5" height="5" fill="url(#g)"/>'
            '<text x="1" y="1" xml:space="preserve">API</text>'
            '<use xlink:href="#g"/><use href="#g"/></g>'
        )
    ).decode()
    for kept in ("<rect", "<text", "API", "linearGradient", "url(#g)", 'href="#g"', "<style>"):
        assert kept in out
    assert out.startswith("<?xml")


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>',
        '<a href="javascript:alert(1)"><rect/></a>',
        '<animate attributeName="href" to="javascript:alert(1)"/>',
        '<set attributeName="onclick" to="alert(1)"/>',
        '<image href="https://evil.example/track.png"/>',
        '<use href="https://evil.example/s.svg#x"/>',
        "<style>@import url(https://evil.example/x.css);</style>",
        "<style>.a{background:url(https://evil.example/t)}</style>",
        '<iframe xmlns="http://www.w3.org/1999/xhtml" src="https://evil.example"/>',
    ],
)
def test_svg_drops_hostile_elements(hostile: str) -> None:
    out = sanitize_svg(svg(f'<rect width="1" height="1"/>{hostile}')).decode()
    assert "<rect" in out
    for bad in ("script", "foreignObject", "javascript", "evil.example", "animate", "<set"):
        assert bad not in out


@pytest.mark.parametrize(
    "attr",
    [
        ' onload="alert(1)"',
        ' ONMOUSEOVER="alert(1)"',
        ' fill="url(https://evil.example/x)"',
        ' style="fill:url(https://evil.example/x)"',
        ' xlink:href="java&#x09;script:alert(1)"',
        ' xmlns:ev="http://www.w3.org/2001/xml-events" ev:event="click"',
    ],
)
def test_svg_drops_hostile_attributes(attr: str) -> None:
    out = sanitize_svg(svg(f'<rect width="1"{attr}/>', root_attrs=attr)).decode()
    assert 'width="1"' in out
    for bad in ("alert", "evil.example", "script", "event"):
        assert bad not in out.lower()


def test_svg_allows_embedded_raster_data() -> None:
    out = sanitize_svg(svg('<image href="data:image/png;base64,iVBORw0KGgo="/>')).decode()
    assert "data:image/png;base64,iVBORw0KGgo=" in out
    out = sanitize_svg(svg('<image href="data:image/svg+xml;base64,PHN2Zz4="/>')).decode()
    assert "data:" not in out


@pytest.mark.parametrize("name", ["diagram.svg", "screen-1.svg"])
def test_demo_svgs_survive(name: str) -> None:
    data = (DEMO / name).read_bytes()
    out = check_image(data)
    assert out.content_type == "image/svg+xml"
    assert out.body.count(b"<") >= data.count(b"<") * 0.9
