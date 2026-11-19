"""Dashboard alerts: at most one open alert per kind."""

from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg.rows import TupleRow

KITE_NOT_CONNECTED = "kite_not_connected"
PRICE_RUN_SKIPPED = "price_run_skipped"


@dataclass(frozen=True)
class Alert:
    kind: str
    message: str
    created_at: datetime


def raise_alert(conn: psycopg.Connection[TupleRow], kind: str, message: str) -> None:
    """Open an alert of this kind, or refresh the message of the open one."""
    conn.execute(
        """
        INSERT INTO alerts (kind, message) VALUES (%s, %s)
        ON CONFLICT (kind) WHERE resolved_at IS NULL DO UPDATE SET message = EXCLUDED.message
        """,
        (kind, message),
    )


def resolve_alert(conn: psycopg.Connection[TupleRow], kind: str) -> None:
    conn.execute(
        "UPDATE alerts SET resolved_at = now() WHERE kind = %s AND resolved_at IS NULL", (kind,)
    )


def open_alerts(conn: psycopg.Connection[TupleRow]) -> list[Alert]:
    rows = conn.execute(
        "SELECT kind, message, created_at FROM alerts WHERE resolved_at IS NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    return [Alert(kind=r[0], message=r[1], created_at=r[2]) for r in rows]
