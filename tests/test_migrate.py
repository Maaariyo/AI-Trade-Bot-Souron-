import psycopg
import pytest
from psycopg.rows import TupleRow

from services.db import connect
from services.migrate import MIGRATIONS_DIR, apply_migrations, migration_files


def test_migration_files_are_numbered_and_sorted() -> None:
    files = migration_files()
    assert files, f"no migrations in {MIGRATIONS_DIR}"
    stems = [f.stem for f in files]
    assert stems == sorted(stems)
    assert all(s[:4].isdigit() for s in stems)


@pytest.mark.integration
def test_requires_autocommit(schema_url: str) -> None:
    with connect(schema_url) as conn, pytest.raises(ValueError):
        apply_migrations(conn)


@pytest.mark.integration
def test_apply_is_idempotent(schema_conn: psycopg.Connection[TupleRow]) -> None:
    first = apply_migrations(schema_conn)
    assert first == [f.stem for f in migration_files()]
    assert apply_migrations(schema_conn) == []


@pytest.mark.integration
def test_job_runs_rejects_unknown_status(schema_conn: psycopg.Connection[TupleRow]) -> None:
    apply_migrations(schema_conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        schema_conn.execute("INSERT INTO job_runs (job_name, status) VALUES ('x', 'done')")
