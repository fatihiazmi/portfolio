"""Admin JSON API for projects, map edges, images, and diagrams. Spec section 9.2, plan T16.

`admin_auth.admin_gate` checks every request before it reaches a route here.
Writes that touch more than one row run in `db.transaction`.

Image rules:

- A new image starts with `scrubbed = 0`. The owner sets it by hand after review (spec 5.1).
- The file goes to R2 first. A row is written only after R2 accepts it.
- Removing an image or a project also removes its R2 objects. An R2 error on a project
  removal is logged, and the row stays removed.
"""

import json
import logging
import secrets
import sqlite3
from collections import defaultdict
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from portfolio_api.db import transaction
from portfolio_api.projects import asset_url
from portfolio_api.r2 import R2, R2Error
from portfolio_api.uploads import MAX_BYTES, CheckedImage, UploadRejected, check_image

log = logging.getLogger("portfolio_api.admin_projects")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _text(min_length: int, max_length: int) -> Any:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=60)]
Title = Annotated[str, _text(1, 120)]
Client = Annotated[str, _text(0, 120)]
Summary = Annotated[str, _text(1, 300)]
Markdown = Annotated[str, StringConstraints(max_length=20_000)]
Tag = Annotated[str, _text(1, 40)]
Stack = Annotated[list[Tag], Field(max_length=20)]
Url = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^https?://\S+$", max_length=300)
]
Key = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[\w][\w./-]*$", max_length=200)
]
Year = Annotated[int, Field(ge=1990, le=2100)]
# Map units. The seeded nodes sit within ±10. NaN and infinity fail the range check.
Coord = Annotated[float, Field(ge=-100, le=100)]
Alt = Annotated[str, _text(1, 300)]
Caption = Annotated[str, _text(0, 500)]
EdgeLabel = Annotated[str, _text(0, 80)]

# Columns that `NOT NULL` in SQLite. A PATCH must not send `null` for these.
PROJECT_NOT_NULL = frozenset(
    {"slug", "title", "kind", "summary", "stack", "sort_order", "published"}
)
IMAGE_NOT_NULL = frozenset({"alt", "sort_order", "scrubbed"})


def _reject_nulls(model: BaseModel, not_null: frozenset[str]) -> None:
    bad = sorted(f for f in model.model_fields_set & not_null if getattr(model, f) is None)
    if bad:
        raise ValueError(f"cannot be null: {', '.join(bad)}")


# --- Models ---


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    title: Title
    client: Client | None = None
    kind: Literal["client", "personal"]
    year: Year | None = None
    summary: Summary
    problem_md: Markdown | None = None
    built_md: Markdown | None = None
    decisions_md: Markdown | None = None
    outcome_md: Markdown | None = None
    stack: Stack = []
    repo_url: Url | None = None
    diagram_key: Key | None = None
    map_x: Coord | None = None
    map_z: Coord | None = None
    # Omitted: the project goes last.
    sort_order: int | None = None
    published: bool = False


class ProjectPatch(BaseModel):
    """Only the fields sent change. `null` clears a nullable field."""

    model_config = ConfigDict(extra="forbid")

    slug: Slug | None = None
    title: Title | None = None
    client: Client | None = None
    kind: Literal["client", "personal"] | None = None
    year: Year | None = None
    summary: Summary | None = None
    problem_md: Markdown | None = None
    built_md: Markdown | None = None
    decisions_md: Markdown | None = None
    outcome_md: Markdown | None = None
    stack: Stack | None = None
    repo_url: Url | None = None
    diagram_key: Key | None = None
    map_x: Coord | None = None
    map_z: Coord | None = None
    sort_order: int | None = None
    published: bool | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "ProjectPatch":
        _reject_nulls(self, PROJECT_NOT_NULL)
        return self


class AdminImage(BaseModel):
    id: int
    project_id: int
    r2_key: str
    url: str
    alt: str
    caption: str | None
    sort_order: int
    scrubbed: bool


class AdminProject(BaseModel):
    id: int
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
    diagram_key: str | None
    diagram_url: str | None
    map_x: float | None
    map_z: float | None
    sort_order: int
    published: bool
    updated_at: str
    images: list[AdminImage]


class AdminEdge(BaseModel):
    from_id: int
    to_id: int
    label: str | None


class AdminProjectList(BaseModel):
    projects: list[AdminProject]
    edges: list[AdminEdge]


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Every project id, first to last.
    ids: Annotated[list[int], Field(max_length=500)]


class EdgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: int
    to_id: int
    label: EdgeLabel | None = None


class EdgesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edges: Annotated[list[EdgeIn], Field(max_length=500)]


class EdgeList(BaseModel):
    edges: list[AdminEdge]


class ImagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alt: Alt | None = None
    caption: Caption | None = None
    sort_order: int | None = None
    scrubbed: bool | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "ImagePatch":
        _reject_nulls(self, IMAGE_NOT_NULL)
        return self


# --- Helpers ---


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _tx(request: Request) -> AbstractContextManager[sqlite3.Connection]:
    return transaction(request.app.state.settings.database_path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _r2(request: Request) -> R2:
    r2: R2 | None = request.app.state.r2
    if r2 is None:
        raise HTTPException(
            503, "Image uploads are not configured. Set the R2_* keys in the API .env."
        )
    return r2


def _not_found(what: str, ident: int) -> HTTPException:
    return HTTPException(404, f"{what} {ident} not found")


def _image(request: Request, row: sqlite3.Row) -> AdminImage:
    return AdminImage(
        id=row["id"],
        project_id=row["project_id"],
        r2_key=row["r2_key"],
        url=asset_url(request, row["r2_key"]),
        alt=row["alt"],
        caption=row["caption"],
        sort_order=row["sort_order"],
        scrubbed=bool(row["scrubbed"]),
    )


def _project(request: Request, row: sqlite3.Row, images: list[AdminImage]) -> AdminProject:
    data = {k: row[k] for k in row.keys()}  # noqa: SIM118 - sqlite3.Row
    diagram = data["diagram_key"]
    return AdminProject(
        **data
        | {
            "stack": json.loads(data["stack"]),
            "published": bool(data["published"]),
            "diagram_url": asset_url(request, diagram) if diagram else None,
            "images": images,
        }
    )


def _projects(
    request: Request, conn: sqlite3.Connection, project_id: int | None = None
) -> list[AdminProject]:
    """All projects in `sort_order`, or the one with `project_id`, with all their images."""
    if project_id is None:
        rows = conn.execute("SELECT * FROM projects ORDER BY sort_order, id").fetchall()
        image_rows = conn.execute(
            "SELECT * FROM project_images ORDER BY project_id, sort_order, id"
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchall()
        image_rows = conn.execute(
            "SELECT * FROM project_images WHERE project_id = ? ORDER BY sort_order, id",
            (project_id,),
        ).fetchall()
    images: dict[int, list[AdminImage]] = defaultdict(list)
    for r in image_rows:
        images[r["project_id"]].append(_image(request, r))
    return [_project(request, r, images[r["id"]]) for r in rows]


def _one_project(request: Request, conn: sqlite3.Connection, project_id: int) -> AdminProject:
    found = _projects(request, conn, project_id)
    if not found:
        raise _not_found("project", project_id)
    return found[0]


def _edges(conn: sqlite3.Connection) -> list[AdminEdge]:
    rows = conn.execute(
        "SELECT from_id, to_id, label FROM project_edges ORDER BY from_id, to_id"
    ).fetchall()
    return [AdminEdge(from_id=r[0], to_id=r[1], label=r[2]) for r in rows]


def _db_value(field: str, value: Any) -> Any:
    """Convert a model value to its SQLite form. An empty optional string becomes NULL."""
    if field == "stack":
        return json.dumps(value)
    if field == "published":
        return int(value)
    if isinstance(value, str) and value == "" and field not in PROJECT_NOT_NULL:
        return None
    return value


def _read_upload(file: UploadFile, *, svg_only: bool = False) -> CheckedImage:
    data = file.file.read(MAX_BYTES + 1)
    try:
        return check_image(data, svg_only=svg_only)
    except UploadRejected as exc:
        raise HTTPException(exc.status, exc.detail) from None


def _new_key(slug: str, ext: str, prefix: str = "") -> str:
    return f"{slug}/{prefix}{secrets.token_hex(8)}.{ext}"


def _put(r2: R2, key: str, image: CheckedImage) -> None:
    try:
        r2.put(key, image.body, image.content_type)
    except R2Error as exc:
        log.error("%s", exc)
        raise HTTPException(502, "Image storage (R2) did not accept the file. Try again.") from None


def _delete_objects(request: Request, keys: list[str]) -> None:
    """Remove R2 objects after their rows are gone. Errors are logged, never raised."""
    r2: R2 | None = request.app.state.r2
    for key in keys:
        if r2 is None:
            log.warning("R2 object %s left in the bucket: R2 is not configured", key)
            continue
        try:
            r2.delete(key)
        except R2Error as exc:
            log.warning("R2 object left in the bucket: %s", exc)


# --- Projects ---


@router.get("/projects", response_model=AdminProjectList)
def list_projects(request: Request) -> AdminProjectList:
    """Every project, drafts included, with all images and every edge."""
    conn = _db(request)
    return AdminProjectList(projects=_projects(request, conn), edges=_edges(conn))


@router.post("/projects", response_model=AdminProject, status_code=201)
def create_project(body: ProjectCreate, request: Request) -> AdminProject:
    values = {f: _db_value(f, v) for f, v in body.model_dump().items()}
    with _tx(request) as tx:
        if values["sort_order"] is None:
            top = tx.execute("SELECT COALESCE(MAX(sort_order), 0) FROM projects").fetchone()[0]
            values["sort_order"] = int(top) + 10
        values["updated_at"] = _now()
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        try:
            cur = tx.execute(
                f"INSERT INTO projects ({cols}) VALUES ({marks})",  # noqa: S608 - model field names
                tuple(values.values()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"slug {body.slug!r} is already used") from None
        project_id = int(cur.lastrowid or 0)
    return _one_project(request, _db(request), project_id)


# Declared before `/projects/{project_id}` so the path reads plainly. The id is an int,
# so "order" never matches it either way.
@router.put("/projects/order", status_code=204)
def save_order(body: OrderIn, request: Request) -> Response:
    """Set `sort_order` to 10, 20, 30... in the order given. `ids` must list every project once."""
    with _tx(request) as tx:
        existing = {r[0] for r in tx.execute("SELECT id FROM projects")}
        sent = set(body.ids)
        if len(sent) != len(body.ids):
            raise HTTPException(422, "ids lists a project more than once")
        if sent != existing:
            missing = sorted(existing - sent)
            unknown = sorted(sent - existing)
            raise HTTPException(
                422, f"ids must list every project once. Missing: {missing}. Unknown: {unknown}."
            )
        tx.executemany(
            "UPDATE projects SET sort_order = ? WHERE id = ?",
            [((i + 1) * 10, pid) for i, pid in enumerate(body.ids)],
        )
    return Response(status_code=204)


@router.get("/projects/{project_id}", response_model=AdminProject)
def get_project(project_id: int, request: Request) -> AdminProject:
    return _one_project(request, _db(request), project_id)


@router.patch("/projects/{project_id}", response_model=AdminProject)
def update_project(project_id: int, body: ProjectPatch, request: Request) -> AdminProject:
    changes = {f: _db_value(f, getattr(body, f)) for f in body.model_fields_set}
    conn = _db(request)
    if changes:
        changes["updated_at"] = _now()
        assignments = ", ".join(f"{f} = ?" for f in changes)
        try:
            cur = conn.execute(
                f"UPDATE projects SET {assignments} WHERE id = ?",  # noqa: S608 - model field names
                (*changes.values(), project_id),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"slug {body.slug!r} is already used") from None
        if cur.rowcount == 0:
            raise _not_found("project", project_id)
    return _one_project(request, conn, project_id)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, request: Request) -> Response:
    """Remove the project, its edges, its image rows, and then its R2 objects."""
    with _tx(request) as tx:
        row = tx.execute("SELECT diagram_key FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise _not_found("project", project_id)
        keys = [
            r[0]
            for r in tx.execute(
                "SELECT r2_key FROM project_images WHERE project_id = ?", (project_id,)
            )
        ]
        if row["diagram_key"]:
            keys.append(row["diagram_key"])
        tx.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    _delete_objects(request, keys)
    return Response(status_code=204)


# --- Edges ---


@router.put("/edges", response_model=EdgeList)
def replace_edges(body: EdgesIn, request: Request) -> EdgeList:
    """Replace every edge. The map draws edges without direction, so A→B and B→A clash."""
    pairs: set[frozenset[int]] = set()
    for e in body.edges:
        if e.from_id == e.to_id:
            raise HTTPException(422, f"edge {e.from_id}→{e.to_id} joins a project to itself")
        pair = frozenset((e.from_id, e.to_id))
        if pair in pairs:
            raise HTTPException(422, f"edge {e.from_id}→{e.to_id} is listed twice")
        pairs.add(pair)
    with _tx(request) as tx:
        existing = {r[0] for r in tx.execute("SELECT id FROM projects")}
        unknown = sorted({i for e in body.edges for i in (e.from_id, e.to_id)} - existing)
        if unknown:
            raise HTTPException(422, f"edges name unknown project ids: {unknown}")
        tx.execute("DELETE FROM project_edges")
        tx.executemany(
            "INSERT INTO project_edges (from_id, to_id, label) VALUES (?, ?, ?)",
            [(e.from_id, e.to_id, e.label or None) for e in body.edges],
        )
    return EdgeList(edges=_edges(_db(request)))


# --- Images and diagrams ---


@router.post("/projects/{project_id}/images", response_model=AdminImage, status_code=201)
def upload_image(
    project_id: int,
    request: Request,
    file: Annotated[UploadFile, File()],
    alt: Annotated[str, Form(max_length=300)],
    caption: Annotated[str | None, Form(max_length=500)] = None,
) -> AdminImage:
    """Upload one image to R2 and add it last, with `scrubbed = 0`."""
    r2 = _r2(request)
    alt = alt.strip()
    caption = (caption or "").strip() or None
    if not alt:
        raise HTTPException(422, "alt must not be empty")
    conn = _db(request)
    project = conn.execute("SELECT slug FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise _not_found("project", project_id)
    image = _read_upload(file)
    key = _new_key(project["slug"], image.ext)
    _put(r2, key, image)
    with _tx(request) as tx:
        top = tx.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM project_images WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        cur = tx.execute(
            "INSERT INTO project_images (project_id, r2_key, alt, caption, sort_order, scrubbed)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            (project_id, key, alt, caption, int(top) + 10),
        )
        tx.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), project_id))
        image_id = int(cur.lastrowid or 0)
    log.info("project %s: image %s uploaded as %s", project_id, image_id, key)
    row = conn.execute("SELECT * FROM project_images WHERE id = ?", (image_id,)).fetchone()
    return _image(request, row)


@router.put("/projects/{project_id}/diagram", response_model=AdminProject)
def upload_diagram(
    project_id: int, request: Request, file: Annotated[UploadFile, File()]
) -> AdminProject:
    """Upload the architecture SVG (spec 5, section 4). Replaces the old diagram."""
    r2 = _r2(request)
    conn = _db(request)
    project = conn.execute(
        "SELECT slug, diagram_key FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if project is None:
        raise _not_found("project", project_id)
    image = _read_upload(file, svg_only=True)
    key = _new_key(project["slug"], image.ext, prefix="diagram-")
    _put(r2, key, image)
    conn.execute(
        "UPDATE projects SET diagram_key = ?, updated_at = ? WHERE id = ?",
        (key, _now(), project_id),
    )
    if project["diagram_key"]:
        _delete_objects(request, [project["diagram_key"]])
    return _one_project(request, conn, project_id)


@router.patch("/images/{image_id}", response_model=AdminImage)
def update_image(image_id: int, body: ImagePatch, request: Request) -> AdminImage:
    changes: dict[str, Any] = {f: getattr(body, f) for f in body.model_fields_set}
    if "scrubbed" in changes:
        changes["scrubbed"] = int(changes["scrubbed"])
    if changes.get("caption") == "":
        changes["caption"] = None
    with _tx(request) as tx:
        row = tx.execute(
            "SELECT project_id FROM project_images WHERE id = ?", (image_id,)
        ).fetchone()
        if row is None:
            raise _not_found("image", image_id)
        if changes:
            assignments = ", ".join(f"{f} = ?" for f in changes)
            tx.execute(
                f"UPDATE project_images SET {assignments} WHERE id = ?",  # noqa: S608 - model field names
                (*changes.values(), image_id),
            )
            tx.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), row["project_id"])
            )
        updated = tx.execute("SELECT * FROM project_images WHERE id = ?", (image_id,)).fetchone()
    if "scrubbed" in changes:
        log.info("image %s: scrubbed set to %s", image_id, changes["scrubbed"])
    return _image(request, updated)


@router.delete("/images/{image_id}", status_code=204)
def delete_image(image_id: int, request: Request) -> Response:
    """Remove the R2 object first. On an R2 error the row stays, so nothing is orphaned."""
    r2 = _r2(request)
    conn = _db(request)
    row = conn.execute(
        "SELECT project_id, r2_key FROM project_images WHERE id = ?", (image_id,)
    ).fetchone()
    if row is None:
        raise _not_found("image", image_id)
    try:
        r2.delete(row["r2_key"])
    except R2Error as exc:
        log.error("%s", exc)
        raise HTTPException(502, "Image storage (R2) did not remove the file. Try again.") from None
    with _tx(request) as tx:
        tx.execute("DELETE FROM project_images WHERE id = ?", (image_id,))
        tx.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (_now(), row["project_id"]))
    return Response(status_code=204)
