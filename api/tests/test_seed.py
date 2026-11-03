import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portfolio_api import db, seed
from portfolio_api.config import Settings
from portfolio_api.main import create_app


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def test_seed_inserts_seven_drafts_and_edges(conn: sqlite3.Connection) -> None:
    assert seed.seed(conn) == (7, len(seed.EDGES))
    rows = conn.execute("SELECT slug, published FROM projects ORDER BY sort_order").fetchall()
    assert [r["slug"] for r in rows] == [
        "sims",
        "nadi",
        "otms",
        "ledger-engine",
        "seatly",
        "shieldwallet",
        "homelab-platform",
    ]
    assert all(r["published"] == 0 for r in rows)


def test_seed_is_idempotent(conn: sqlite3.Connection) -> None:
    seed.seed(conn)
    assert seed.seed(conn) == (0, 0)
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 7


def test_seed_keeps_owner_edits(conn: sqlite3.Connection) -> None:
    seed.seed(conn)
    conn.execute("UPDATE projects SET summary = 'edited', published = 1 WHERE slug = 'sims'")
    seed.seed(conn)
    row = conn.execute("SELECT summary, published FROM projects WHERE slug = 'sims'").fetchone()
    assert (row["summary"], row["published"]) == ("edited", 1)


def test_seed_client_projects_have_no_repo(conn: sqlite3.Connection) -> None:
    seed.seed(conn)
    rows = conn.execute("SELECT kind, repo_url FROM projects").fetchall()
    assert all(r["repo_url"] is None for r in rows if r["kind"] == "client")
    assert all(r["repo_url"] for r in rows if r["kind"] == "personal")


def test_drafts_hidden_until_published(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "s.db")
    seed.main(["--db", str(settings.database_path)])
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects").json()["projects"] == []


def test_publish_flag_exposes_map_data(tmp_path: Path) -> None:
    settings = Settings(database_path=tmp_path / "s.db")
    seed.main(["--db", str(settings.database_path), "--publish"])
    with TestClient(create_app(settings)) as client:
        body = client.get("/api/projects").json()
    assert len(body["projects"]) == 7
    assert len(body["edges"]) == len(seed.EDGES)
    assert all(p["map_x"] is not None and p["map_z"] is not None for p in body["projects"])
