"""job_runs bookkeeping shared by every scheduled job."""

from datetime import date, datetime
from typing import Literal

import psycopg
from psycopg.rows import TupleRow

Status = Literal["running", "succeeded", "failed", "skipped"]


def start_run(conn: psycopg.Connection[TupleRow], job: str, *, at: datetime) -> int:
    row = conn.execute(
        "INSERT INTO job_runs (job_name, status, started_at) VALUES (%s, 'running', %s) "
        "RETURNING id",
        (job, at),
    ).fetchone()
    assert row is not None
    return int(row[0])


def finish_run(
    conn: psycopg.Connection[TupleRow], run_id: int, status: Status, detail: str | None = None
) -> None:
    conn.execute(
        "UPDATE job_runs SET status = %s, detail = %s, finished_at = now() WHERE id = %s",
        (status, detail, run_id),
    )


def record_run(
    conn: psycopg.Connection[TupleRow],
    job: str,
    status: Status,
    detail: str | None = None,
    *,
    at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO job_runs (job_name, status, detail, started_at, finished_at) "
        "VALUES (%s, %s, %s, %s, now())",
        (job, status, detail, at),
    )


def has_run_on(
    conn: psycopg.Connection[TupleRow], job: str, ist_day: date, statuses: tuple[Status, ...]
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM job_runs WHERE job_name = %s AND status = ANY(%s) "
        "AND (started_at AT TIME ZONE 'Asia/Kolkata')::date = %s LIMIT 1",
        (job, list(statuses), ist_day),
    ).fetchone()
    return row is not None
