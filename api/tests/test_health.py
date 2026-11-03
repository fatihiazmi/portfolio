import sqlite3

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_health_503_when_db_closed(client: TestClient) -> None:
    db: sqlite3.Connection = client.app.state.db
    db.close()
    res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json() == {"ok": False}


def test_cors_allows_pages_origin_only(client: TestClient) -> None:
    ok = client.get("/api/health", headers={"Origin": "https://fatihiazmi.dev"})
    assert ok.headers.get("access-control-allow-origin") == "https://fatihiazmi.dev"

    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
