"""Seed the 7 map projects as drafts. Plan T7.

Run: `python -m portfolio_api.seed` (uses `DATABASE_PATH`).
Local only: add `--publish` to mark the seeded rows published, for Astro dev.
Local only: add `--demo` to add `template-demo`, a published project that fills every
case study field (spec section 5). Its image files live in `api/demo/`.

Inserts are keyed on `slug` and never overwrite an existing row, so a run after
the owner edits a project in the admin changes nothing.

All text here is a draft. The owner replaces it in T19. Client project facts that
are not confirmed stay NULL: `client`, and every `*_md` field.
"""

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from portfolio_api.config import get_settings
from portfolio_api.db import connect, migrate


class SeedProject(TypedDict):
    slug: str
    title: str
    kind: str
    year: int
    summary: str
    stack: list[str]
    repo_url: str | None
    map_x: float
    map_z: float
    sort_order: int


_CLIENT_STACK = ["React", "TypeScript", "Supabase", "PostgreSQL"]
_GITHUB = "https://github.com/fatihiazmi"

# Order follows spec 3.1: SiMS, NADI, OTMS, then personal repos.
PROJECTS: list[SeedProject] = [
    {
        "slug": "sims",
        "title": "SiMS",
        "kind": "client",
        "year": 2026,
        "summary": "Maintenance management system (CMMS) for road assets.",
        "stack": _CLIENT_STACK,
        "repo_url": None,
        "map_x": -6.0,
        "map_z": -2.0,
        "sort_order": 10,
    },
    {
        "slug": "nadi",
        "title": "NADI",
        "kind": "client",
        "year": 2025,
        "summary": "Management system for the NADI community digital centre network.",
        "stack": _CLIENT_STACK,
        "repo_url": None,
        "map_x": -2.0,
        "map_z": 2.0,
        "sort_order": 20,
    },
    {
        "slug": "otms",
        "title": "OTMS",
        "kind": "client",
        "year": 2025,
        "summary": "Overtime management system tied to attendance and payroll.",
        "stack": _CLIENT_STACK,
        "repo_url": None,
        "map_x": 2.0,
        "map_z": -3.0,
        "sort_order": 30,
    },
    {
        "slug": "ledger-engine",
        "title": "ledger-engine",
        "kind": "personal",
        "year": 2026,
        "summary": "Double-entry payment ledger with event sourcing and CQRS.",
        "stack": ["Go", "DDD", "Event Sourcing", "CQRS", "Property-based testing"],
        "repo_url": f"{_GITHUB}/ledger-engine",
        "map_x": 7.0,
        "map_z": 1.0,
        "sort_order": 40,
    },
    {
        "slug": "seatly",
        "title": "seatly",
        "kind": "personal",
        "year": 2026,
        "summary": "Cinema seat reservation with atomic multi-seat holds and idempotent payment.",
        "stack": ["Laravel", "PHP", "PostgreSQL", "Vue 3", "Inertia.js"],
        "repo_url": f"{_GITHUB}/seatly",
        "map_x": 9.0,
        "map_z": -4.0,
        "sort_order": 50,
    },
    {
        "slug": "shieldwallet",
        "title": "shieldwallet",
        "kind": "personal",
        "year": 2026,
        "summary": "Multi-layer fraud detection for e-wallets, built for TNG Digital FINHACK 2026.",
        "stack": ["Python"],
        "repo_url": f"{_GITHUB}/shieldwallet",
        "map_x": 10.0,
        "map_z": 5.0,
        "sort_order": 60,
    },
    {
        "slug": "homelab-platform",
        "title": "Homelab Platform",
        "kind": "personal",
        "year": 2026,
        "summary": "The platform this site runs on: Proxmox, Cloudflare Tunnel, Litestream, "
        "Prometheus and Grafana as code.",
        "stack": ["Proxmox", "Docker", "Cloudflare Tunnel", "Litestream", "Prometheus", "Grafana"],
        "repo_url": f"{_GITHUB}/portfolio",
        "map_x": 0.0,
        "map_z": 8.0,
        "sort_order": 70,
    },
]

# (from slug, to slug, label). Edges join projects that share a domain or technique (spec 4.1).
EDGES: list[tuple[str, str, str]] = [
    ("otms", "nadi", "payroll, attendance"),
    ("sims", "nadi", "asset management"),
    ("seatly", "ledger-engine", "idempotent payments"),
    ("shieldwallet", "ledger-engine", "payment transactions"),
]


# Local demo for the case study template (plan T13). Text describes the template only.
# No position on the map: it shows in the node list and on `/work/template-demo`.
DEMO_SLUG = "template-demo"
DEMO_PROJECT = {
    "slug": DEMO_SLUG,
    "title": "Template demo",
    "client": "Demo client",
    "kind": "client",
    "year": 2026,
    "summary": "Local demo project. It fills every case study field for a template check.",
    "problem_md": (
        "The client needed one place to see every open job. Teams tracked work in"
        " spreadsheets, and nobody knew which jobs were late.\n\n"
        "This paragraph is demo text. Real case studies replace it in plan T19."
    ),
    "built_md": (
        "- **Job register** with status, owner, and due date\n"
        "- **Approvals** in two steps, with an audit trail\n"
        "- **Reports** exported as CSV for finance\n"
    ),
    "decisions_md": (
        "1. **PostgreSQL row-level security.** Each site sees only its own jobs.\n"
        "2. **Server-side pagination.** Lists stay fast past 100 000 rows.\n"
        "3. **`idempotency_key` on writes.** A double tap never creates two jobs.\n"
    ),
    "outcome_md": (
        "- **12** sites on the system\n"
        "- **40 000** jobs recorded\n"
        "- Demo numbers only. See [the plan](https://github.com/fatihiazmi).\n"
    ),
    "stack": ["React", "TypeScript", "PostgreSQL"],
    "diagram_key": f"{DEMO_SLUG}/diagram.svg",
}
DEMO_IMAGES = [
    (f"{DEMO_SLUG}/screen-1.svg", "Demo screenshot: job list", "Job list with filters."),
    (f"{DEMO_SLUG}/screen-2.svg", "Demo screenshot: approval form", "Two-step approval."),
    (f"{DEMO_SLUG}/screen-3.svg", "Demo screenshot: report export", None),
]


def seed_demo(conn: sqlite3.Connection) -> bool:
    """Insert the published demo project and its scrubbed images. False when it exists."""
    conn.execute("BEGIN")
    try:
        d = DEMO_PROJECT
        cur = conn.execute(
            "INSERT INTO projects (slug, title, client, kind, year, summary, problem_md,"
            " built_md, decisions_md, outcome_md, stack, diagram_key, sort_order, published,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 999, 1, ?)"
            " ON CONFLICT (slug) DO NOTHING",
            (
                d["slug"],
                d["title"],
                d["client"],
                d["kind"],
                d["year"],
                d["summary"],
                d["problem_md"],
                d["built_md"],
                d["decisions_md"],
                d["outcome_md"],
                json.dumps(d["stack"]),
                d["diagram_key"],
                datetime.now(UTC).isoformat(),
            ),
        )
        if cur.rowcount:
            pid = cur.lastrowid
            conn.executemany(
                "INSERT INTO project_images (project_id, r2_key, alt, caption, sort_order,"
                " scrubbed) VALUES (?, ?, ?, ?, ?, 1)",
                [(pid, key, alt, cap, i) for i, (key, alt, cap) in enumerate(DEMO_IMAGES)],
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return bool(cur.rowcount)


def seed(conn: sqlite3.Connection, *, publish: bool = False) -> tuple[int, int]:
    """Insert missing projects and edges in one transaction.

    Returns (projects inserted, edges inserted). Existing rows stay unchanged.
    """
    now = datetime.now(UTC).isoformat()
    inserted_projects = 0
    inserted_edges = 0
    conn.execute("BEGIN")
    try:
        for p in PROJECTS:
            cur = conn.execute(
                "INSERT INTO projects (slug, title, kind, year, summary, stack, repo_url,"
                " map_x, map_z, sort_order, published, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (slug) DO NOTHING",
                (
                    p["slug"],
                    p["title"],
                    p["kind"],
                    p["year"],
                    p["summary"],
                    json.dumps(p["stack"]),
                    p["repo_url"],
                    p["map_x"],
                    p["map_z"],
                    p["sort_order"],
                    int(publish),
                    now,
                ),
            )
            inserted_projects += cur.rowcount
        ids = {r["slug"]: r["id"] for r in conn.execute("SELECT id, slug FROM projects")}
        for source, target, label in EDGES:
            cur = conn.execute(
                "INSERT OR IGNORE INTO project_edges (from_id, to_id, label) VALUES (?, ?, ?)",
                (ids[source], ids[target], label),
            )
            inserted_edges += cur.rowcount
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return inserted_projects, inserted_edges


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the 7 map projects as drafts.")
    parser.add_argument("--db", type=Path, help="SQLite file. Default: DATABASE_PATH.")
    parser.add_argument(
        "--publish", action="store_true", help="Mark new rows published. Local dev only."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help=f"Add the published `{DEMO_SLUG}` project. Local dev only.",
    )
    args = parser.parse_args(argv)
    conn = connect(args.db or get_settings().database_path)
    migrate(conn)
    projects, edges = seed(conn, publish=args.publish)
    demo = seed_demo(conn) if args.demo else False
    conn.close()
    state = "published" if args.publish else "draft"
    print(f"seeded {projects} projects ({state}) and {edges} edges")
    if demo:
        print(f"seeded demo project {DEMO_SLUG} (published)")


if __name__ == "__main__":
    main()
