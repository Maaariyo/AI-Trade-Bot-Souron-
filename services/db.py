"""Postgres connections. All services share this one entry point."""

import psycopg
from psycopg.rows import TupleRow

from services.config import get_settings


def connect(url: str | None = None, *, connect_timeout: int = 5) -> psycopg.Connection[TupleRow]:
    """Open a connection to `url`, or to DATABASE_URL from settings."""
    return psycopg.connect(url or get_settings().database_url, connect_timeout=connect_timeout)
