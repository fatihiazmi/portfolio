import sqlite3
from pathlib import Path

import pytest

from portfolio_api import db

NOW = "2026-11-03T00:00:00+00:00"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def _project(conn: sqlite3.Connection, slug: str, **overrides: object) -> int:
    row = {"slug": slug, "title": slug, "kind": "client", "summary": "s", "updated_at": NOW}
    row.update(overrides)
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    cur = conn.execute(f"INSERT INTO projects ({cols}) VALUES ({marks})", tuple(row.values()))  # noqa: S608
    return int(cur.lastrowid or 0)


def test_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_creates_spec_tables(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"projects", "project_edges", "project_images", "leads", "schema_migrations"} <= tables


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    c = db.connect(tmp_path / "t.db")
    assert db.migrate(c) == ["0001_init"]
    assert db.migrate(c) == []


def test_project_kind_check(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _project(conn, "bad", kind="secret")


def test_project_stack_must_be_json_array(conn: sqlite3.Connection) -> None:
    _project(conn, "ok", stack='["React", "Supabase"]')
    with pytest.raises(sqlite3.IntegrityError):
        _project(conn, "bad", stack='{"not": "array"}')


def test_slug_unique(conn: sqlite3.Connection) -> None:
    _project(conn, "sims")
    with pytest.raises(sqlite3.IntegrityError):
        _project(conn, "sims")


def test_edge_rejects_self_loop(conn: sqlite3.Connection) -> None:
    pid = _project(conn, "otms")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project_edges (from_id, to_id) VALUES (?, ?)", (pid, pid))


def test_delete_project_cascades(conn: sqlite3.Connection) -> None:
    a = _project(conn, "nadi")
    b = _project(conn, "otms")
    conn.execute("INSERT INTO project_edges (from_id, to_id) VALUES (?, ?)", (a, b))
    conn.execute(
        "INSERT INTO project_images (project_id, r2_key, alt) VALUES (?, ?, ?)", (a, "k", "alt")
    )
    conn.execute("DELETE FROM projects WHERE id = ?", (a,))
    assert conn.execute("SELECT COUNT(*) FROM project_edges").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM project_images").fetchone()[0] == 0


def test_lead_kind_and_status_checks(conn: sqlite3.Connection) -> None:
    sql = (
        "INSERT INTO leads (created_at, name, email, kind, message, ip_hash, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    conn.execute(sql, (NOW, "n", "e@x.com", "freelance", "m", "h", "new"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (NOW, "n", "e@x.com", "spam", "m", "h", "new"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, (NOW, "n", "e@x.com", "hiring", "m", "h", "deleted"))


def test_failed_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    real = db._migration_files()
    broken = ("0002_broken", "CREATE TABLE extra (id INTEGER);\nTHIS IS NOT SQL;")
    monkeypatch.setattr(db, "_migration_files", lambda: [*real, broken])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(c)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "extra" not in tables
    versions = {r[0] for r in c.execute("SELECT version FROM schema_migrations")}
    assert versions == {"0001_init"}
