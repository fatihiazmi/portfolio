import sqlite3

import pytest
from fastapi.testclient import TestClient

NOW = "2026-11-03T00:00:00+00:00"


def _project(db: sqlite3.Connection, slug: str, *, published: bool, **overrides: object) -> int:
    row = {
        "slug": slug,
        "title": slug.upper(),
        "kind": "client",
        "summary": f"{slug} summary",
        "stack": '["React", "Supabase"]',
        "published": int(published),
        "updated_at": NOW,
    }
    row.update(overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = db.execute(f"INSERT INTO projects ({cols}) VALUES ({marks})", tuple(row.values()))  # noqa: S608
    return int(cur.lastrowid or 0)


def _image(
    db: sqlite3.Connection, project_id: int, key: str, *, scrubbed: bool, order: int
) -> None:
    db.execute(
        "INSERT INTO project_images (project_id, r2_key, alt, caption, sort_order, scrubbed)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, key, f"alt {key}", None, order, int(scrubbed)),
    )


def _edge(db: sqlite3.Connection, a: int, b: int, label: str) -> None:
    db.execute("INSERT INTO project_edges (from_id, to_id, label) VALUES (?, ?, ?)", (a, b, label))


@pytest.fixture
def db(client: TestClient) -> sqlite3.Connection:
    return client.app.state.db


@pytest.fixture
def seeded(db: sqlite3.Connection) -> dict[str, int]:
    """Two published projects, one draft, edges to both, mixed images."""
    ids = {
        "otms": _project(db, "otms", published=True, sort_order=20, diagram_key="d/otms.svg"),
        "sims": _project(db, "sims", published=True, sort_order=10),
        "secret": _project(db, "secret", published=False, sort_order=5),
    }
    _edge(db, ids["otms"], ids["sims"], "shared")
    _edge(db, ids["otms"], ids["secret"], "to draft")
    _image(db, ids["otms"], "otms/2.png", scrubbed=True, order=2)
    _image(db, ids["otms"], "otms/1.png", scrubbed=True, order=1)
    _image(db, ids["otms"], "otms/raw.png", scrubbed=False, order=0)
    _image(db, ids["secret"], "secret/1.png", scrubbed=True, order=0)
    return ids


def test_list_returns_published_only_in_sort_order(
    client: TestClient, seeded: dict[str, int]
) -> None:
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert [p["slug"] for p in res.json()["projects"]] == ["sims", "otms"]


def test_list_hides_edges_to_drafts(client: TestClient, seeded: dict[str, int]) -> None:
    edges = client.get("/api/projects").json()["edges"]
    assert edges == [{"source": "otms", "target": "sims", "label": "shared"}]


def test_list_returns_scrubbed_images_only_in_order(
    client: TestClient, seeded: dict[str, int]
) -> None:
    otms = next(p for p in client.get("/api/projects").json()["projects"] if p["slug"] == "otms")
    assert [i["url"] for i in otms["images"]] == [
        "https://img.test/otms/1.png",
        "https://img.test/otms/2.png",
    ]
    assert otms["images"][0]["alt"] == "alt otms/1.png"


def test_project_shape(client: TestClient, seeded: dict[str, int]) -> None:
    body = client.get("/api/projects/otms").json()
    assert body["stack"] == ["React", "Supabase"]
    assert body["diagram_url"] == "https://img.test/d/otms.svg"
    for internal in ("id", "published", "sort_order", "diagram_key"):
        assert internal not in body


def test_get_published_project(client: TestClient, seeded: dict[str, int]) -> None:
    res = client.get("/api/projects/sims")
    assert res.status_code == 200
    assert res.json()["slug"] == "sims"
    assert res.json()["diagram_url"] is None


def test_get_unknown_slug_404(client: TestClient, seeded: dict[str, int]) -> None:
    res = client.get("/api/projects/nope")
    assert res.status_code == 404
    assert res.json() == {"detail": "project not found"}


def test_get_draft_404_same_as_unknown(client: TestClient, seeded: dict[str, int]) -> None:
    draft = client.get("/api/projects/secret")
    unknown = client.get("/api/projects/nope")
    assert draft.status_code == 404
    assert draft.json() == unknown.json()


def test_list_empty(client: TestClient) -> None:
    assert client.get("/api/projects").json() == {"projects": [], "edges": []}


def test_cors_on_projects(client: TestClient, seeded: dict[str, int]) -> None:
    ok = client.get("/api/projects", headers={"Origin": "https://fatihiazmi.dev"})
    assert ok.headers.get("access-control-allow-origin") == "https://fatihiazmi.dev"
    other = client.get("/api/projects", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
