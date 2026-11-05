"""Admin JSON API: identity, dashboard summary, leads, and publish. Spec section 9.2.

`admin_auth.admin_gate` checks every request under `/api/admin` before it reaches a route here.
Projects, edges, and images live in `admin_projects`.

Publish (spec 2.1 and 5.1):

1. `PAGES_DEPLOY_HOOK_URL` unset: 503.
2. Any image of a published project has `scrubbed = 0`: 409 with those image IDs.
   Draft projects never block: the Pages build cannot see them.
3. POST the Pages deploy hook. An error: 502. Every hook call is logged in `publishes`.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from portfolio_api.config import Settings

log = logging.getLogger("portfolio_api.admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])

LeadKind = Literal["freelance", "hiring", "other"]
LeadStatus = Literal["new", "replied", "closed"]


class Me(BaseModel):
    email: str


class Publish(BaseModel):
    id: int
    created_at: str
    ok: bool
    deploy_id: str | None
    error: str | None


class LeadCounts(BaseModel):
    new: int
    total: int


class ProjectCounts(BaseModel):
    total: int
    published: int


class Summary(BaseModel):
    leads: LeadCounts
    projects: ProjectCounts
    # Unscrubbed images on published projects. Above 0, publish returns 409.
    blocking_images: int
    last_publish: Publish | None
    # Time of the last Litestream upload to R2. Prometheus records it as
    # `portfolio:litestream_last_upload_timestamp_seconds` (T20). The API reads it once it
    # has a Prometheus client in T22. Null until then.
    last_backup_at: str | None


class Lead(BaseModel):
    id: int
    created_at: str
    name: str
    email: str
    company: str | None
    kind: LeadKind
    budget: str | None
    message: str
    status: LeadStatus


class LeadList(BaseModel):
    leads: list[Lead]
    # Rows matching the filters, before `limit` and `offset`.
    total: int


class LeadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LeadStatus


_LEAD_COLUMNS = "id, created_at, name, email, company, kind, budget, message, status"


def _db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


def _publish(row: sqlite3.Row) -> Publish:
    return Publish(
        id=row["id"],
        created_at=row["created_at"],
        ok=bool(row["ok"]),
        deploy_id=row["deploy_id"],
        error=row["error"],
    )


def _lead(row: sqlite3.Row) -> Lead:
    return Lead(**{k: row[k] for k in row.keys()})  # noqa: SIM118 - sqlite3.Row


def _blocking_images(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT i.id FROM project_images i JOIN projects p ON p.id = i.project_id"
        " WHERE p.published = 1 AND i.scrubbed = 0 ORDER BY i.id"
    ).fetchall()
    return [r[0] for r in rows]


@router.get("/me")
def me(request: Request) -> Me:
    """The logged-in admin. The SPA shows it in the header."""
    return Me(email=request.state.admin_email)


@router.get("/summary", response_model=Summary)
def summary(request: Request) -> Summary:
    """Dashboard numbers."""
    conn = _db(request)
    leads = conn.execute("SELECT COALESCE(SUM(status = 'new'), 0), COUNT(*) FROM leads").fetchone()
    projects = conn.execute("SELECT COUNT(*), COALESCE(SUM(published), 0) FROM projects").fetchone()
    last = conn.execute(
        "SELECT * FROM publishes WHERE ok = 1 ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return Summary(
        leads=LeadCounts(new=leads[0], total=leads[1]),
        projects=ProjectCounts(total=projects[0], published=projects[1]),
        blocking_images=len(_blocking_images(conn)),
        last_publish=_publish(last) if last else None,
        last_backup_at=None,
    )


# --- Leads ---


@router.get("/leads", response_model=LeadList)
def list_leads(
    request: Request,
    kind: LeadKind | None = None,
    status: LeadStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    """Leads, newest first. The IP hash never leaves the database."""
    where: list[str] = []
    params: list[str | int] = []
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if status:
        where.append("status = ?")
        params.append(status)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    conn = _db(request)
    total = conn.execute(f"SELECT COUNT(*) FROM leads{clause}", params).fetchone()[0]  # noqa: S608 - fixed fragments
    rows = conn.execute(
        f"SELECT {_LEAD_COLUMNS} FROM leads{clause}"  # noqa: S608 - fixed fragments
        " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return LeadList(leads=[_lead(r) for r in rows], total=total)


@router.patch("/leads/{lead_id}", response_model=Lead)
def update_lead(lead_id: int, body: LeadPatch, request: Request) -> Lead:
    conn = _db(request)
    cur = conn.execute("UPDATE leads SET status = ? WHERE id = ?", (body.status, lead_id))
    if cur.rowcount == 0:
        raise HTTPException(404, f"lead {lead_id} not found")
    row = conn.execute(
        f"SELECT {_LEAD_COLUMNS} FROM leads WHERE id = ?",  # noqa: S608 - constant column list
        (lead_id,),
    ).fetchone()
    return _lead(row)


# --- Publish ---


def _record(
    conn: sqlite3.Connection, *, ok: bool, deploy_id: str | None, error: str | None
) -> Publish:
    cur = conn.execute(
        "INSERT INTO publishes (created_at, ok, deploy_id, error) VALUES (?, ?, ?, ?)",
        (datetime.now(UTC).isoformat(), int(ok), deploy_id, error),
    )
    row = conn.execute("SELECT * FROM publishes WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _publish(row)


def _deploy_id(res: httpx.Response) -> str | None:
    """Cloudflare answers `{"success": true, "result": {"id": ...}}`. Any other shape: None."""
    try:
        body = res.json()
    except ValueError:
        return None
    result = body.get("result") if isinstance(body, dict) else None
    deploy_id = result.get("id") if isinstance(result, dict) else None
    return deploy_id if isinstance(deploy_id, str) else None


@router.post("/publish", response_model=Publish)
def publish(request: Request) -> Publish | JSONResponse:
    """Check the scrubbed rule, then start a Pages build through the deploy hook."""
    settings: Settings = request.app.state.settings
    if not settings.pages_deploy_hook_url:
        raise HTTPException(503, "Publish is not configured. Set PAGES_DEPLOY_HOOK_URL.")
    conn = _db(request)
    blocked = _blocking_images(conn)
    if blocked:
        log.info("publish blocked: unscrubbed images %s", blocked)
        return JSONResponse(
            {
                "detail": "Published projects have images not marked scrubbed. "
                "Review each one, then set scrubbed.",
                "image_ids": blocked,
            },
            status_code=409,
        )
    http: httpx.Client = request.app.state.http
    try:
        res = http.post(settings.pages_deploy_hook_url)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        # The hook URL is a secret. Log the error type and status only.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        error = f"{type(exc).__name__}, HTTP {status}" if status else type(exc).__name__
        log.error("publish: deploy hook failed: %s", error)
        _record(conn, ok=False, deploy_id=None, error=error)
        raise HTTPException(502, f"Pages deploy hook failed ({error}). Try again.") from None
    record = _record(conn, ok=True, deploy_id=_deploy_id(res), error=None)
    log.info("publish: Pages build started, deploy %s", record.deploy_id)
    return record
