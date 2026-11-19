"""Shared fixtures. Integration tests need TEST_DATABASE_URL (make test sets it)."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.db import connect
from services.migrate import apply_migrations


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; run `make test` to start Postgres")
    return url


@pytest.fixture
def schema_url(pg_url: str) -> Iterator[str]:
    """A connection URL pinned to a fresh, throwaway schema."""
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with connect(pg_url) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    sep = "&" if "?" in pg_url else "?"
    yield f"{pg_url}{sep}options=-csearch_path%3D{schema}"
    with connect(pg_url) as admin:
        admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.fixture
def schema_conn(schema_url: str) -> Iterator[psycopg.Connection[TupleRow]]:
    conn = connect(schema_url)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db(schema_conn: psycopg.Connection[TupleRow]) -> psycopg.Connection[TupleRow]:
    """An autocommit connection to a throwaway schema with every migration applied."""
    apply_migrations(schema_conn)
    return schema_conn
