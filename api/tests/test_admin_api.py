"""Admin JSON API tests. Spec section 9.2, plan T16.

The Access JWT check has its own tests in `test_admin_auth.py`. Here a stub verifier
accepts the token `ok`, so each test exercises one endpoint past the gate.
R2 and the Pages deploy hook are mocked with one `httpx.MockTransport`.
"""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from portfolio_api.admin_auth import AccessDenied
from portfolio_api.config import Settings
from portfolio_api.main import create_app

EMAIL = "owner@example.com"
R2_HOST = "acct.r2.cloudflarestorage.com"
HOOK = "https://api.cloudflare.com/client/v4/pages/webhooks/deploy_hooks/hook-id"
NOW = "2026-11-04T00:00:00+00:00"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1"/><script>alert(1)</script></svg>'
HEADERS = {"Cf-Access-Jwt-Assertion": "ok", "X-Requested-With": "admin"}


class StubAccess:
    def verify(self, token: str) -> str:
        if token != "ok":
            raise AccessDenied("bad token")
        return EMAIL


class Upstream:
    """Mock R2 and deploy hook. Records each request. Set a status to fail one service."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.r2_status = 200
        self.hook_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == R2_HOST:
            status = (
                self.r2_status
                if self.r2_status != 200
                else (204 if request.method == "DELETE" else 200)
            )
            return httpx.Response(status)
        if str(request.url) == HOOK and request.method == "POST":
            body = {"success": True, "result": {"id": "deploy-1"}}
            return httpx.Response(self.hook_status, json=body)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    def r2(self, method: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == R2_HOST and r.method == method]

    def hook_calls(self) -> int:
        return sum(1 for r in self.requests if str(r.url) == HOOK)


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_path": tmp_path / "admin.db",
        "images_base_url": "https://img.test",
        "r2_account_id": "acct",
        "r2_access_key_id": "AKID",
        "r2_secret_access_key": "secret",
        "r2_images_bucket": "images",
        "pages_deploy_hook_url": HOOK,
    }
    return Settings(**values | overrides)


def _client(settings: Settings, upstream: Upstream) -> TestClient:
    http = httpx.Client(transport=httpx.MockTransport(upstream))
    return TestClient(create_app(settings, http=http))


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def api(tmp_path: Path, upstream: Upstream) -> Iterator[TestClient]:
    with _client(_settings(tmp_path), upstream) as c:
        c.app.state.access = StubAccess()
        c.headers.update(HEADERS)
        yield c


@pytest.fixture
def bare(tmp_path: Path, upstream: Upstream) -> Iterator[TestClient]:
    """No R2 keys and no deploy hook."""
    settings = _settings(
        tmp_path,
        r2_account_id="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_images_bucket="",
        pages_deploy_hook_url="",
    )
    with _client(settings, upstream) as c:
        c.app.state.access = StubAccess()
        c.headers.update(HEADERS)
        yield c


@pytest.fixture
def db(api: TestClient) -> sqlite3.Connection:
    return api.app.state.db


def _project(db: sqlite3.Connection, slug: str, *, published: bool = False, **extra: Any) -> int:
    row = {
        "slug": slug,
        "title": slug.upper(),
        "kind": "client",
        "summary": f"{slug} summary",
        "published": int(published),
        "updated_at": NOW,
    } | extra
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = db.execute(f"INSERT INTO projects ({cols}) VALUES ({marks})", tuple(row.values()))  # noqa: S608
    return int(cur.lastrowid or 0)


def _image(db: sqlite3.Connection, project_id: int, key: str, *, scrubbed: bool) -> int:
    cur = db.execute(
        "INSERT INTO project_images (project_id, r2_key, alt, scrubbed) VALUES (?, ?, ?, ?)",
        (project_id, key, f"alt {key}", int(scrubbed)),
    )
    return int(cur.lastrowid or 0)


def _lead(db: sqlite3.Connection, name: str, *, kind: str, status: str, at: str) -> int:
    cur = db.execute(
        "INSERT INTO leads (created_at, name, email, kind, message, ip_hash, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (at, name, f"{name}@example.com", kind, "message " * 5, "hash", status),
    )
    return int(cur.lastrowid or 0)


def _upload(api: TestClient, project_id: int, data: bytes = PNG, **form: str) -> httpx.Response:
    return api.post(
        f"/api/admin/projects/{project_id}/images",
        files={"file": ("x.bin", data, "application/octet-stream")},
        data={"alt": "Job list", **form},
    )


# --- Gate: every endpoint ---

ENDPOINTS = [
    ("GET", "/api/admin/summary"),
    ("GET", "/api/admin/projects"),
    ("POST", "/api/admin/projects"),
    ("GET", "/api/admin/projects/1"),
    ("PATCH", "/api/admin/projects/1"),
    ("DELETE", "/api/admin/projects/1"),
    ("PUT", "/api/admin/projects/order"),
    ("PUT", "/api/admin/edges"),
    ("POST", "/api/admin/projects/1/images"),
    ("PUT", "/api/admin/projects/1/diagram"),
    ("PATCH", "/api/admin/images/1"),
    ("DELETE", "/api/admin/images/1"),
    ("GET", "/api/admin/leads"),
    ("PATCH", "/api/admin/leads/1"),
    ("POST", "/api/admin/publish"),
]


@pytest.mark.parametrize(("method", "path"), ENDPOINTS)
def test_every_endpoint_needs_login(api: TestClient, method: str, path: str) -> None:
    res = api.request(method, path, headers={"Cf-Access-Jwt-Assertion": ""})
    assert res.status_code == 403


@pytest.mark.parametrize(("method", "path"), [e for e in ENDPOINTS if e[0] != "GET"])
def test_every_write_needs_the_header(api: TestClient, method: str, path: str) -> None:
    res = api.request(method, path, headers={"X-Requested-With": ""})
    assert res.status_code == 403


# --- Summary ---


def test_summary_counts(api: TestClient, db: sqlite3.Connection) -> None:
    live = _project(db, "live", published=True)
    draft = _project(db, "draft")
    _image(db, live, "live/raw.png", scrubbed=False)
    _image(db, draft, "draft/raw.png", scrubbed=False)
    _lead(db, "a", kind="hiring", status="new", at=NOW)
    _lead(db, "b", kind="other", status="replied", at=NOW)
    body = api.get("/api/admin/summary").json()
    assert body == {
        "leads": {"new": 1, "total": 2},
        "projects": {"total": 2, "published": 1},
        "blocking_images": 1,
        "last_publish": None,
        "last_backup_at": None,
    }


def test_summary_shows_last_successful_publish(api: TestClient, upstream: Upstream) -> None:
    assert api.post("/api/admin/publish").status_code == 200
    upstream.hook_status = 500
    assert api.post("/api/admin/publish").status_code == 502
    last = api.get("/api/admin/summary").json()["last_publish"]
    assert last["ok"] is True
    assert last["deploy_id"] == "deploy-1"


# --- Projects ---


def test_list_includes_drafts_images_and_edges(api: TestClient, db: sqlite3.Connection) -> None:
    a = _project(db, "a", published=True, sort_order=20)
    b = _project(db, "b", sort_order=10, diagram_key="b/d.svg")
    _image(db, a, "a/1.png", scrubbed=False)
    db.execute("INSERT INTO project_edges (from_id, to_id, label) VALUES (?, ?, 'x')", (a, b))
    body = api.get("/api/admin/projects").json()
    assert [p["slug"] for p in body["projects"]] == ["b", "a"]
    draft, live = body["projects"]
    assert draft["published"] is False
    assert draft["diagram_url"] == "https://img.test/b/d.svg"
    assert live["images"][0]["scrubbed"] is False
    assert live["images"][0]["url"] == "https://img.test/a/1.png"
    assert body["edges"] == [{"from_id": a, "to_id": b, "label": "x"}]


def test_create_project(api: TestClient, db: sqlite3.Connection) -> None:
    _project(db, "first", sort_order=40)
    res = api.post(
        "/api/admin/projects",
        json={
            "slug": "new-one",
            "title": " New ",
            "kind": "personal",
            "summary": "A summary.",
            "stack": ["Go", " SQL "],
            "repo_url": "https://github.com/x/new-one",
            "map_x": 1.5,
            "client": "",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "New"
    assert body["stack"] == ["Go", "SQL"]
    assert body["sort_order"] == 50
    assert body["published"] is False
    assert body["client"] is None
    assert body["images"] == []


@pytest.mark.parametrize(
    "patch",
    [
        {"slug": "Bad Slug"},
        {"slug": "-x"},
        {"kind": "secret"},
        {"summary": ""},
        {"repo_url": "javascript:alert(1)"},
        {"map_x": 1000},
        {"year": 1800},
        {"stack": [""]},
        {"unknown": 1},
    ],
)
def test_create_rejects_bad_fields(api: TestClient, patch: dict[str, Any]) -> None:
    body = {"slug": "ok", "title": "T", "kind": "client", "summary": "S"} | patch
    assert api.post("/api/admin/projects", json=body).status_code == 422


def test_create_duplicate_slug_is_409(api: TestClient, db: sqlite3.Connection) -> None:
    _project(db, "taken")
    body = {"slug": "taken", "title": "T", "kind": "client", "summary": "S"}
    assert api.post("/api/admin/projects", json=body).status_code == 409


def test_get_project(api: TestClient, db: sqlite3.Connection) -> None:
    pid = _project(db, "one")
    assert api.get(f"/api/admin/projects/{pid}").json()["slug"] == "one"
    assert api.get("/api/admin/projects/999").status_code == 404


def test_patch_project(api: TestClient, db: sqlite3.Connection) -> None:
    pid = _project(db, "one", client="Old client", problem_md="old")
    res = api.patch(
        f"/api/admin/projects/{pid}",
        json={"title": "Renamed", "client": None, "published": True, "map_z": -2},
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["title"], body["client"], body["published"], body["map_z"]) == (
        "Renamed",
        None,
        True,
        -2.0,
    )
    assert body["problem_md"] == "old"
    assert body["updated_at"] > NOW


@pytest.mark.parametrize("field", ["title", "slug", "stack", "published", "sort_order"])
def test_patch_null_on_required_field_is_422(
    api: TestClient, db: sqlite3.Connection, field: str
) -> None:
    pid = _project(db, "one")
    assert api.patch(f"/api/admin/projects/{pid}", json={field: None}).status_code == 422


def test_patch_slug_conflict_and_unknown_id(api: TestClient, db: sqlite3.Connection) -> None:
    _project(db, "a")
    b = _project(db, "b")
    assert api.patch(f"/api/admin/projects/{b}", json={"slug": "a"}).status_code == 409
    assert api.patch("/api/admin/projects/999", json={"title": "x"}).status_code == 404
    assert api.patch("/api/admin/projects/999", json={}).status_code == 404


def test_delete_project_removes_rows_and_objects(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    pid = _project(db, "gone", diagram_key="gone/diagram-1.svg")
    other = _project(db, "kept")
    _image(db, pid, "gone/1.png", scrubbed=True)
    db.execute("INSERT INTO project_edges (from_id, to_id) VALUES (?, ?)", (pid, other))
    assert api.delete(f"/api/admin/projects/{pid}").status_code == 204
    assert db.execute("SELECT COUNT(*) FROM project_images").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM project_edges").fetchone()[0] == 0
    deleted = {r.url.path for r in upstream.r2("DELETE")}
    assert deleted == {"/images/gone/1.png", "/images/gone/diagram-1.svg"}
    assert api.delete(f"/api/admin/projects/{pid}").status_code == 404


def test_delete_project_keeps_going_when_r2_fails(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    pid = _project(db, "gone")
    _image(db, pid, "gone/1.png", scrubbed=True)
    upstream.r2_status = 500
    assert api.delete(f"/api/admin/projects/{pid}").status_code == 204
    assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


# --- Order ---


def test_save_order(api: TestClient, db: sqlite3.Connection) -> None:
    a, b, c = (_project(db, s) for s in "abc")
    assert api.put("/api/admin/projects/order", json={"ids": [c, a, b]}).status_code == 204
    slugs = [p["slug"] for p in api.get("/api/admin/projects").json()["projects"]]
    assert slugs == ["c", "a", "b"]
    orders = [r[0] for r in db.execute("SELECT sort_order FROM projects ORDER BY sort_order")]
    assert orders == [10, 20, 30]


@pytest.mark.parametrize("ids", [[1, 2], [1, 2, 3, 3], [1, 2, 3, 99]])
def test_save_order_needs_every_id_once(
    api: TestClient, db: sqlite3.Connection, ids: list[int]
) -> None:
    for s in "abc":
        _project(db, s, sort_order=5)
    assert api.put("/api/admin/projects/order", json={"ids": ids}).status_code == 422
    assert {r[0] for r in db.execute("SELECT sort_order FROM projects")} == {5}


# --- Edges ---


def test_replace_edges(api: TestClient, db: sqlite3.Connection) -> None:
    a, b, c = (_project(db, s) for s in "abc")
    db.execute("INSERT INTO project_edges (from_id, to_id) VALUES (?, ?)", (a, b))
    res = api.put(
        "/api/admin/edges",
        json={"edges": [{"from_id": b, "to_id": c, "label": "shared"}, {"from_id": a, "to_id": c}]},
    )
    assert res.status_code == 200
    assert res.json()["edges"] == [
        {"from_id": a, "to_id": c, "label": None},
        {"from_id": b, "to_id": c, "label": "shared"},
    ]
    assert api.put("/api/admin/edges", json={"edges": []}).json() == {"edges": []}


@pytest.mark.parametrize(
    "edges",
    [
        [{"from_id": 1, "to_id": 1}],
        [{"from_id": 1, "to_id": 2}, {"from_id": 2, "to_id": 1}],
        [{"from_id": 1, "to_id": 99}],
    ],
    ids=["self-loop", "reverse-duplicate", "unknown-id"],
)
def test_replace_edges_rejects_bad_lists(
    api: TestClient, db: sqlite3.Connection, edges: list[dict[str, int]]
) -> None:
    a, b = _project(db, "a"), _project(db, "b")
    db.execute("INSERT INTO project_edges (from_id, to_id) VALUES (?, ?)", (a, b))
    assert api.put("/api/admin/edges", json={"edges": edges}).status_code == 422
    assert db.execute("SELECT COUNT(*) FROM project_edges").fetchone()[0] == 1


# --- Images ---


def test_upload_image(api: TestClient, db: sqlite3.Connection, upstream: Upstream) -> None:
    pid = _project(db, "sims")
    _image(db, pid, "sims/old.png", scrubbed=True)
    res = _upload(api, pid, caption=" Filters ")
    assert res.status_code == 201
    body = res.json()
    assert body["r2_key"].startswith("sims/") and body["r2_key"].endswith(".png")
    assert body["url"] == f"https://img.test/{body['r2_key']}"
    assert (body["alt"], body["caption"], body["scrubbed"], body["sort_order"]) == (
        "Job list",
        "Filters",
        False,
        10,
    )
    (put,) = upstream.r2("PUT")
    assert put.url.path == f"/images/{body['r2_key']}"
    assert put.headers["content-type"] == "image/png"
    assert put.content == PNG


def test_upload_svg_is_sanitised(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    pid = _project(db, "sims")
    body = _upload(api, pid, SVG).json()
    assert body["r2_key"].endswith(".svg")
    (put,) = upstream.r2("PUT")
    assert put.headers["content-type"] == "image/svg+xml"
    assert b"<rect" in put.content
    assert b"script" not in put.content


@pytest.mark.parametrize(
    ("data", "form", "status"),
    [
        (b"GIF89a" + b"\x00" * 10, {}, 415),
        (PNG + b"\x00" * (5 * 1024 * 1024), {}, 413),
        (PNG, {"alt": "   "}, 422),
    ],
    ids=["gif", "too-large", "blank-alt"],
)
def test_upload_rejects_bad_files(
    api: TestClient,
    db: sqlite3.Connection,
    upstream: Upstream,
    data: bytes,
    form: dict[str, str],
    status: int,
) -> None:
    pid = _project(db, "sims")
    assert _upload(api, pid, data, **form).status_code == status
    assert upstream.r2("PUT") == []
    assert db.execute("SELECT COUNT(*) FROM project_images").fetchone()[0] == 0


def test_upload_r2_error_stores_nothing(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    pid = _project(db, "sims")
    upstream.r2_status = 403
    assert _upload(api, pid).status_code == 502
    assert db.execute("SELECT COUNT(*) FROM project_images").fetchone()[0] == 0


def test_upload_unknown_project_is_404(api: TestClient) -> None:
    assert _upload(api, 999).status_code == 404


def test_upload_without_r2_is_503(bare: TestClient) -> None:
    pid = _project(bare.app.state.db, "sims")
    assert _upload(bare, pid).status_code == 503


def test_upload_diagram(api: TestClient, db: sqlite3.Connection, upstream: Upstream) -> None:
    pid = _project(db, "sims", diagram_key="sims/diagram-old.svg")
    res = api.put(
        f"/api/admin/projects/{pid}/diagram", files={"file": ("d.svg", SVG, "image/svg+xml")}
    )
    assert res.status_code == 200
    key = res.json()["diagram_key"]
    assert key.startswith("sims/diagram-") and key.endswith(".svg")
    assert res.json()["diagram_url"] == f"https://img.test/{key}"
    assert [r.url.path for r in upstream.r2("DELETE")] == ["/images/sims/diagram-old.svg"]
    png = api.put(f"/api/admin/projects/{pid}/diagram", files={"file": ("d.png", PNG)})
    assert png.status_code == 415
    missing = api.put("/api/admin/projects/999/diagram", files={"file": ("d.svg", SVG)})
    assert missing.status_code == 404


def test_patch_image(api: TestClient, db: sqlite3.Connection) -> None:
    pid = _project(db, "sims")
    iid = _image(db, pid, "sims/1.png", scrubbed=False)
    res = api.patch(
        f"/api/admin/images/{iid}",
        json={"scrubbed": True, "alt": "New alt", "caption": "", "sort_order": 3},
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["scrubbed"], body["alt"], body["caption"], body["sort_order"]) == (
        True,
        "New alt",
        None,
        3,
    )
    updated = db.execute("SELECT updated_at FROM projects WHERE id = ?", (pid,)).fetchone()[0]
    assert updated > NOW


@pytest.mark.parametrize("body", [{"alt": None}, {"alt": ""}, {"scrubbed": None}, {"x": 1}])
def test_patch_image_rejects_bad_fields(
    api: TestClient, db: sqlite3.Connection, body: dict[str, Any]
) -> None:
    iid = _image(db, _project(db, "sims"), "sims/1.png", scrubbed=False)
    assert api.patch(f"/api/admin/images/{iid}", json=body).status_code == 422


def test_patch_unknown_image_is_404(api: TestClient) -> None:
    assert api.patch("/api/admin/images/999", json={"scrubbed": True}).status_code == 404


def test_delete_image(api: TestClient, db: sqlite3.Connection, upstream: Upstream) -> None:
    iid = _image(db, _project(db, "sims"), "sims/1.png", scrubbed=True)
    assert api.delete(f"/api/admin/images/{iid}").status_code == 204
    assert [r.url.path for r in upstream.r2("DELETE")] == ["/images/sims/1.png"]
    assert api.delete(f"/api/admin/images/{iid}").status_code == 404


def test_delete_image_r2_error_keeps_row(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    iid = _image(db, _project(db, "sims"), "sims/1.png", scrubbed=True)
    upstream.r2_status = 500
    assert api.delete(f"/api/admin/images/{iid}").status_code == 502
    assert db.execute("SELECT COUNT(*) FROM project_images").fetchone()[0] == 1


# --- Leads ---


@pytest.fixture
def leads(db: sqlite3.Connection) -> dict[str, int]:
    return {
        "old": _lead(db, "old", kind="hiring", status="closed", at="2026-11-01T00:00:00+00:00"),
        "mid": _lead(db, "mid", kind="freelance", status="new", at="2026-11-02T00:00:00+00:00"),
        "new": _lead(db, "new", kind="freelance", status="new", at="2026-11-03T00:00:00+00:00"),
    }


def test_list_leads_newest_first_without_ip_hash(api: TestClient, leads: dict[str, int]) -> None:
    body = api.get("/api/admin/leads").json()
    assert body["total"] == 3
    assert [lead["name"] for lead in body["leads"]] == ["new", "mid", "old"]
    assert "ip_hash" not in body["leads"][0]


@pytest.mark.parametrize(
    ("query", "names", "total"),
    [
        ("kind=freelance", ["new", "mid"], 2),
        ("status=closed", ["old"], 1),
        ("kind=freelance&status=new&limit=1", ["new"], 2),
        ("limit=1&offset=1", ["mid"], 3),
    ],
)
def test_list_leads_filters(
    api: TestClient, leads: dict[str, int], query: str, names: list[str], total: int
) -> None:
    body = api.get(f"/api/admin/leads?{query}").json()
    assert [lead["name"] for lead in body["leads"]] == names
    assert body["total"] == total


@pytest.mark.parametrize("query", ["kind=spam", "status=gone", "limit=0", "limit=500"])
def test_list_leads_rejects_bad_filters(api: TestClient, query: str) -> None:
    assert api.get(f"/api/admin/leads?{query}").status_code == 422


def test_patch_lead_status(api: TestClient, leads: dict[str, int]) -> None:
    res = api.patch(f"/api/admin/leads/{leads['new']}", json={"status": "replied"})
    assert res.status_code == 200
    assert res.json()["status"] == "replied"
    bad = api.patch(f"/api/admin/leads/{leads['new']}", json={"status": "spam"})
    assert bad.status_code == 422
    assert api.patch("/api/admin/leads/999", json={"status": "closed"}).status_code == 404


# --- Publish ---


def test_publish_calls_the_deploy_hook(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    live = _project(db, "live", published=True)
    _image(db, live, "live/ok.png", scrubbed=True)
    # A draft's unscrubbed image never blocks: the Pages build cannot see drafts.
    _image(db, _project(db, "draft"), "draft/raw.png", scrubbed=False)
    res = api.post("/api/admin/publish")
    assert res.status_code == 200
    body = res.json()
    assert (body["ok"], body["deploy_id"], body["error"]) == (True, "deploy-1", None)
    assert upstream.hook_calls() == 1


def test_publish_blocked_by_unscrubbed_images(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    a = _project(db, "a", published=True)
    b = _project(db, "b", published=True)
    _image(db, a, "a/ok.png", scrubbed=True)
    raw_a = _image(db, a, "a/raw.png", scrubbed=False)
    raw_b = _image(db, b, "b/raw.png", scrubbed=False)
    res = api.post("/api/admin/publish")
    assert res.status_code == 409
    assert res.json()["image_ids"] == [raw_a, raw_b]
    assert upstream.hook_calls() == 0
    assert db.execute("SELECT COUNT(*) FROM publishes").fetchone()[0] == 0


def test_publish_hook_error_is_502_and_logged(
    api: TestClient, db: sqlite3.Connection, upstream: Upstream
) -> None:
    upstream.hook_status = 500
    res = api.post("/api/admin/publish")
    assert res.status_code == 502
    assert HOOK not in res.text
    row = db.execute("SELECT ok, error FROM publishes").fetchone()
    assert (row[0], row[1]) == (0, "HTTPStatusError, HTTP 500")


def test_publish_without_hook_is_503(bare: TestClient) -> None:
    assert bare.post("/api/admin/publish").status_code == 503
