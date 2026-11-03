"""SQLite access: connection setup and forward-only SQL migrations."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

MIGRATIONS_PACKAGE = "portfolio_api.migrations"


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys, and a busy timeout.

    `isolation_level=None` turns off Python's implicit transactions. Each
    statement commits on its own. Multi-statement writes use explicit `BEGIN`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _migration_files() -> list[tuple[str, str]]:
    """Return (version, sql) pairs sorted by file name, e.g. `0001_init.sql`."""
    files = [f for f in resources.files(MIGRATIONS_PACKAGE).iterdir() if f.name.endswith(".sql")]
    return [
        (f.name.removesuffix(".sql"), f.read_text()) for f in sorted(files, key=lambda f: f.name)
    ]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations in order. Returns the versions applied in this call.

    Each migration runs in its own transaction. A failed migration rolls back
    and raises, leaving earlier migrations applied.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL)"
    )
    done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    applied: list[str] = []
    for version, sql in _migration_files():
        if version in done:
            continue
        try:
            conn.execute("BEGIN")
            for statement in _split_statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        applied.append(version)
    return applied


def _split_statements(sql: str) -> Iterator[str]:
    """Split a migration file into statements.

    `executescript` is avoided because it commits implicitly and breaks the
    per-migration transaction. Migrations must not contain triggers or `;`
    inside string literals.
    """
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            yield "\n".join(buffer)
            buffer = []
    if buffer:
        yield "\n".join(buffer)
