"""Admin SPA serving tests. Plan T17. The Access check has its own tests in `test_admin_auth.py`."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portfolio_api.admin_auth import AccessDenied
from portfolio_api.config import Settings
from portfolio_api.main import create_app

INDEX = "<!doctype html><div id=app></div>"


class StubAccess:
    def verify(self, token: str) -> str:
        if token != "ok":
            raise AccessDenied("bad token")
        return "owner@example.com"


def _client(tmp_path: Path, ui_dir: Path) -> TestClient:
    settings = Settings(database_path=tmp_path / "ui.db", admin_ui_dir=ui_dir)
    return TestClient(create_app(settings), follow_redirects=False)


@pytest.fixture
def build(tmp_path: Path) -> Path:
    ui = tmp_path / "admin"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text(INDEX)
    (ui / "assets" / "index-abc123.js").write_text("console.log(1)")
    (ui / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside the build")
    return ui


@pytest.fixture
def ui(tmp_path: Path, build: Path) -> Iterator[TestClient]:
    with _client(tmp_path, build) as c:
        c.app.state.access = StubAccess()
        c.headers["Cf-Access-Jwt-Assertion"] = "ok"
        yield c


def test_root_redirects_to_slash(ui: TestClient) -> None:
    res = ui.get("/admin")
    assert res.status_code == 307
    assert res.headers["location"] == "/admin/"


@pytest.mark.parametrize("path", ["/admin/", "/admin/projects", "/admin/projects/3"])
def test_app_routes_return_index(ui: TestClient, path: str) -> None:
    res = ui.get(path)
    assert res.status_code == 200
    assert res.text == INDEX
    assert res.headers["cache-control"] == "no-cache"


def test_hashed_asset_is_cached(ui: TestClient) -> None:
    res = ui.get("/admin/assets/index-abc123.js")
    assert res.status_code == 200
    assert res.text == "console.log(1)"
    assert "immutable" in res.headers["cache-control"]


def test_other_file_is_not_cached(ui: TestClient) -> None:
    res = ui.get("/admin/favicon.svg")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-cache"


def test_missing_file_is_404(ui: TestClient) -> None:
    assert ui.get("/admin/assets/gone-123.js").status_code == 404


@pytest.mark.parametrize("path", ["/admin/../secret.txt", "/admin/%2e%2e/secret.txt"])
def test_path_outside_build_is_never_served(ui: TestClient, path: str) -> None:
    res = ui.get(path)
    assert "outside the build" not in res.text


def test_no_build_is_503(tmp_path: Path) -> None:
    with _client(tmp_path, tmp_path / "missing") as c:
        c.app.state.access = StubAccess()
        res = c.get("/admin/", headers={"Cf-Access-Jwt-Assertion": "ok"})
    assert res.status_code == 503
    assert "pnpm build" in res.json()["detail"]


def test_gate_still_applies(tmp_path: Path, build: Path) -> None:
    with _client(tmp_path, build) as c:
        c.app.state.access = StubAccess()
        assert c.get("/admin/").status_code == 403
        assert c.get("/admin/assets/index-abc123.js").status_code == 403
