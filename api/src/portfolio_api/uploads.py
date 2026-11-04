"""Image upload checks. Spec section 11.

- Types: PNG, JPEG, WebP, SVG only. The type comes from the file bytes, never from
  the client's `Content-Type` or file name.
- Size: 5 MB max.
- SVG: parsed with `defusedxml` (no DTD, no entities), then cut down to an allowlist
  of SVG elements. Scripts, event attributes, external references, and foreign
  namespaces are removed. The cleaned SVG is what goes to R2.

Raster images are stored byte for byte. Metadata such as JPEG EXIF is not stripped.
"""

import re
import xml.etree.ElementTree as ET  # noqa: S405 - serialising only. Parsing uses defusedxml.
from dataclasses import dataclass

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

MAX_BYTES = 5 * 1024 * 1024

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

# Static drawing elements only. Animation elements (`animate`, `set`) are out because
# they can rewrite `href` at runtime. `a`, `script`, `foreignObject`, `iframe` are out.
SVG_ELEMENTS = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "switch", "title", "desc", "style",
        "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
        "text", "tspan", "textPath", "image", "marker", "pattern", "clipPath", "mask",
        "linearGradient", "radialGradient", "stop", "filter",
        "feBlend", "feColorMatrix", "feComponentTransfer", "feComposite", "feDropShadow",
        "feFlood", "feFuncA", "feFuncB", "feFuncG", "feFuncR", "feGaussianBlur",
        "feMerge", "feMergeNode", "feMorphology", "feOffset",
    }
)  # fmt: skip
ATTR_NAMESPACES = frozenset({"", XLINK_NS, XML_NS})
# `url(` that points anywhere but a local `#id`, or a CSS `@import`.
EXTERNAL_REF = re.compile(r"url\(\s*['\"]?\s*(?!#)|@import", re.IGNORECASE)
SAFE_HREF = re.compile(r"^(#[\w.:-]+|data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+)$")
BAD_SCHEME = re.compile(r"(javascript|vbscript|data:text)", re.IGNORECASE)
CONTROL = re.compile(r"[\s\x00-\x1f]+")


class UploadRejected(Exception):
    """The file cannot be stored. `status` is the HTTP status to return."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class CheckedImage:
    body: bytes
    content_type: str
    ext: str


def _split(name: str) -> tuple[str, str]:
    """Split `{ns}local` into (ns, local). A name without a namespace has ns ''."""
    if name.startswith("{"):
        ns, _, local = name[1:].partition("}")
        return ns, local
    return "", name


def _sniff_raster(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def _clean_attrs(el: ET.Element) -> None:
    for name in list(el.attrib):
        ns, local = _split(name)
        value = el.attrib[name]
        squashed = CONTROL.sub("", value)
        drop = (
            ns not in ATTR_NAMESPACES
            or local.lower().startswith("on")
            or BAD_SCHEME.search(squashed) is not None
            or EXTERNAL_REF.search(value) is not None
            or (local == "href" and SAFE_HREF.match(value.strip()) is None)
        )
        if drop:
            del el.attrib[name]


def _clean(el: ET.Element) -> None:
    for child in list(el):
        ns, local = _split(child.tag) if isinstance(child.tag, str) else ("", "")
        if ns != SVG_NS or local not in SVG_ELEMENTS:
            el.remove(child)
            continue
        if local == "style" and child.text and EXTERNAL_REF.search(child.text):
            el.remove(child)
            continue
        _clean(child)
    _clean_attrs(el)


def sanitize_svg(data: bytes) -> bytes:
    """Return a cleaned copy of an SVG file. Raise `UploadRejected` for anything else."""
    try:
        root = fromstring(data, forbid_dtd=True)
    except (ET.ParseError, DefusedXmlException, ValueError) as exc:
        raise UploadRejected(415, f"File is not PNG, JPEG, WebP, or a valid SVG: {exc}") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise UploadRejected(415, f'SVG root must be <svg xmlns="{SVG_NS}">. Found <{root.tag}>.')
    _clean(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def check_image(data: bytes, *, svg_only: bool = False) -> CheckedImage:
    """Check type and size. SVGs come back sanitised."""
    if len(data) > MAX_BYTES:
        raise UploadRejected(413, f"File is {len(data)} bytes. The limit is {MAX_BYTES} (5 MB).")
    if not data:
        raise UploadRejected(422, "File is empty.")
    raster = _sniff_raster(data)
    if raster is not None:
        if svg_only:
            raise UploadRejected(415, f"Diagrams must be SVG. This file is {raster[0]}.")
        return CheckedImage(body=data, content_type=raster[0], ext=raster[1])
    return CheckedImage(body=sanitize_svg(data), content_type="image/svg+xml", ext="svg")
