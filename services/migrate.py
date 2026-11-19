"""Apply plain-SQL migrations from db/migrations in filename order.

Each file runs once, inside its own transaction, and is recorded in
schema_migrations. An advisory lock lets the api and worker containers both
call this at startup without racing. Run with: python -m services.migrate
"""

import logging
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from services.db import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
_LOCK_ID = 7_301_2026  # arbitrary, constant across services

log = logging.getLogger(__name__)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def apply_migrations(
    conn: psycopg.Connection[TupleRow], directory: Path = MIGRATIONS_DIR
) -> list[str]:
    """Apply pending migrations and return the versions applied, in order.

    `conn` must be in autocommit mode so each migration commits on its own.
    """
    if not conn.autocommit:
        raise ValueError("apply_migrations needs an autocommit connection")
    applied_now: list[str] = []
    conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_ID,))
    try:
        with conn.transaction():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version    text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for path in migration_files(directory):
            version = path.stem
            if version in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
            log.info("applied migration %s", version)
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_ID,))
    return applied_now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with connect() as conn:
        conn.autocommit = True
        applied = apply_migrations(conn)
    log.info("migrations up to date (%d applied now)", len(applied))


if __name__ == "__main__":
    main()
