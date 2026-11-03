"""Public read API for projects. Spec section 9.1.

Only published projects leave this module. Drafts return 404, the same as an
unknown slug, so the API never confirms that a draft exists.
Only images marked `scrubbed` are returned (spec 5.1), even on a published project.
"""

import json
import sqlite3
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["projects"])

_PROJECT_COLUMNS = (
    "id, slug, title, client, kind, year, summary, problem_md, built_md, decisions_md,"
    " outcome_md, stack, repo_url, diagram_key, map_x, map_z, updated_at"
)


class Image(BaseModel):
    url: str
    alt: str
    caption: str | None


class Project(BaseModel):
    slug: str
    title: str
    client: str | None
    kind: Literal["client", "personal"]
    year: int | None
    summary: str
    problem_md: str | None
    built_md: str | None
    decisions_md: str | None
    outcome_md: str | None
    stack: list[str]
    repo_url: str | None
    diagram_url: str | None
    map_x: float | None
    map_z: float | None
    updated_at: str
    images: list[Image]


class Edge(BaseModel):
    source: str
    target: str
    label: str | None


class ProjectList(BaseModel):
    projects: list[Project]
    edges: list[Edge]


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _asset_url(request: Request, key: str) -> str:
    base: str = request.app.state.settings.images_base_url
    return f"{base.rstrip('/')}/{quote(key)}"


def _images(
    request: Request, conn: sqlite3.Connection, project_ids: list[int]
) -> dict[int, list[Image]]:
    """Scrubbed images per project, in `sort_order`."""
    by_project: dict[int, list[Image]] = {pid: [] for pid in project_ids}
    if not project_ids:
        return by_project
    marks = ", ".join("?" for _ in project_ids)
    sql = (
        "SELECT project_id, r2_key, alt, caption FROM project_images"  # noqa: S608 - placeholders only
        f" WHERE scrubbed = 1 AND project_id IN ({marks})"
        " ORDER BY project_id, sort_order, id"
    )
    rows = conn.execute(sql, project_ids).fetchall()
    for row in rows:
        by_project[row["project_id"]].append(
            Image(url=_asset_url(request, row["r2_key"]), alt=row["alt"], caption=row["caption"])
        )
    return by_project


def _project(request: Request, row: sqlite3.Row, images: list[Image]) -> Project:
    data = {k: row[k] for k in row.keys() if k not in ("id", "stack", "diagram_key")}  # noqa: SIM118 - sqlite3.Row
    diagram = row["diagram_key"]
    return Project(
        **data,
        stack=json.loads(row["stack"]),
        diagram_url=_asset_url(request, diagram) if diagram else None,
        images=images,
    )


@router.get("", response_model=ProjectList)
def list_projects(request: Request) -> ProjectList:
    """Published projects in `sort_order`, with scrubbed images and edges between them."""
    conn = _db(request)
    rows = conn.execute(
        f"SELECT {_PROJECT_COLUMNS} FROM projects"  # noqa: S608 - constant column list
        " WHERE published = 1 ORDER BY sort_order, id"
    ).fetchall()
    images = _images(request, conn, [r["id"] for r in rows])
    edges = conn.execute(
        "SELECT f.slug AS source, t.slug AS target, e.label FROM project_edges e"
        " JOIN projects f ON f.id = e.from_id"
        " JOIN projects t ON t.id = e.to_id"
        " WHERE f.published = 1 AND t.published = 1"
        " ORDER BY f.sort_order, f.id, t.sort_order, t.id"
    ).fetchall()
    return ProjectList(
        projects=[_project(request, r, images[r["id"]]) for r in rows],
        edges=[Edge(source=e["source"], target=e["target"], label=e["label"]) for e in edges],
    )


@router.get("/{slug}", response_model=Project)
def get_project(slug: str, request: Request) -> Project:
    """One published project. 404 for an unknown slug and for a draft."""
    conn = _db(request)
    row = conn.execute(
        f"SELECT {_PROJECT_COLUMNS} FROM projects"  # noqa: S608 - constant column list
        " WHERE slug = ? AND published = 1",
        (slug,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _project(request, row, _images(request, conn, [row["id"]])[row["id"]])
