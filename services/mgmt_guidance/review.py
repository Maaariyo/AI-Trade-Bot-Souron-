"""Owner review of guidance rows (Phase 1b), and the only reader Agent 7 may use.

The owner approves or rejects extracted rows, or enters a row by hand from a
stored document (the free path). Hand-entered rows must still pass the quote
check. `usable_guidance` returns only QUOTE_VERIFIED and HUMAN_REVIEWED rows
(CLAUDE.md rule 10).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from services.mgmt_guidance.extract import Metric, StatedUnit
from services.mgmt_guidance.quote_check import canonical, check_quote

REVIEWABLE = ("EXTRACTED", "QUOTE_VERIFIED")
USABLE = ("QUOTE_VERIFIED", "HUMAN_REVIEWED")


class ReviewError(ValueError):
    pass


@dataclass(frozen=True)
class GuidanceView:
    id: int
    isin: str
    document_id: int
    method: str
    stated_on: date
    metric: str
    metric_detail: str | None
    target_period: str
    target_low_stated: Decimal
    target_high_stated: Decimal
    unit_stated: str
    quote: str
    page_no: int | None
    status: str
    flag: str | None
    review_note: str | None


_COLUMNS = (
    "id, isin, document_id, method, stated_on, metric, metric_detail, target_period, "
    "target_low_stated, target_high_stated, unit_stated, quote, page_no, status, flag, review_note"
)


def list_guidance(
    conn: psycopg.Connection[TupleRow],
    *,
    status: str | None = None,
    isin: str | None = None,
    limit: int = 200,
) -> list[GuidanceView]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM mgmt_guidance "
        "WHERE (%(status)s::text IS NULL OR status = %(status)s) "
        "AND (%(isin)s::text IS NULL OR isin = %(isin)s) "
        "ORDER BY status = 'EXTRACTED' DESC, stated_on DESC, id LIMIT %(limit)s",
        {"status": status, "isin": isin, "limit": limit},
    ).fetchall()
    return [GuidanceView(*r) for r in rows]


def usable_guidance(conn: psycopg.Connection[TupleRow], isin: str) -> list[GuidanceView]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM mgmt_guidance "
        "WHERE isin = %s AND status = ANY(%s) ORDER BY stated_on, id",
        (isin, list(USABLE)),
    ).fetchall()
    return [GuidanceView(*r) for r in rows]


def _set_status(
    conn: psycopg.Connection[TupleRow],
    guidance_id: int,
    status: str,
    note: str | None,
    now: datetime,
) -> None:
    row = conn.execute(
        "SELECT status, flag FROM mgmt_guidance WHERE id = %s", (guidance_id,)
    ).fetchone()
    if row is None:
        raise ReviewError(f"no guidance row {guidance_id}")
    if row[0] not in REVIEWABLE:
        raise ReviewError(f"row {guidance_id} is already {row[0]}")
    if status == "HUMAN_REVIEWED" and row[1] and row[0] == "EXTRACTED" and not (note or "").strip():
        raise ReviewError(f"row {guidance_id} is flagged ({row[1]}); add a note to approve it")
    conn.execute(
        "UPDATE mgmt_guidance SET status = %s, pre_review_status = status, review_note = %s, "
        "reviewed_at = %s WHERE id = %s",
        (status, note, now, guidance_id),
    )


def approve(
    conn: psycopg.Connection[TupleRow], guidance_id: int, *, note: str | None, now: datetime
) -> None:
    _set_status(conn, guidance_id, "HUMAN_REVIEWED", note, now)


def reject(
    conn: psycopg.Connection[TupleRow], guidance_id: int, *, note: str | None, now: datetime
) -> None:
    _set_status(conn, guidance_id, "REJECTED", note, now)


def add_manual(
    conn: psycopg.Connection[TupleRow],
    *,
    document_id: int,
    metric: Metric,
    target_period: str,
    target_low: Decimal,
    target_high: Decimal,
    unit: StatedUnit,
    quote: str,
    now: datetime,
    metric_detail: str | None = None,
    note: str | None = None,
) -> int:
    """A row typed by the owner. Its quote must be found in the stored document."""
    doc = conn.execute(
        "SELECT isin, doc_date FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    if doc is None:
        raise ReviewError(f"no document {document_id}")
    pages = [
        r[0]
        for r in conn.execute(
            "SELECT text FROM document_pages WHERE document_id = %s ORDER BY page_no",
            (document_id,),
        ).fetchall()
    ]
    low, high = sorted((target_low, target_high))
    result = check_quote(quote, pages, sorted({low, high}))
    if not result.verified:
        raise ReviewError(f"quote check failed: {result.flag}")
    c_low, c_unit = canonical(low, unit)
    c_high, _ = canonical(high, unit)
    row = conn.execute(
        """
        INSERT INTO mgmt_guidance (isin, document_id, method, stated_on, metric, metric_detail,
            target_period, target_low_stated, target_high_stated, unit_stated, target_low,
            target_high, unit, quote, page_no, status, review_note, reviewed_at)
        VALUES (%s, %s, 'manual', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            'HUMAN_REVIEWED', %s, %s)
        RETURNING id
        """,
        (
            doc[0],
            document_id,
            doc[1],
            metric,
            metric_detail,
            target_period,
            low,
            high,
            unit,
            c_low,
            c_high,
            c_unit,
            quote,
            result.page_no,
            note,
            now,
        ),
    ).fetchone()
    assert row is not None
    return int(row[0])


@dataclass(frozen=True)
class ReviewStats:
    by_status: dict[str, int]
    llm_reviewed: int
    llm_approved: int
    verified_reviewed: int
    verified_approved: int

    @property
    def agreement(self) -> float | None:
        """Share of reviewed QUOTE_VERIFIED rows the owner approved (done-when: >= 90%)."""
        if not self.verified_reviewed:
            return None
        return self.verified_approved / self.verified_reviewed


def review_stats(conn: psycopg.Connection[TupleRow]) -> ReviewStats:
    by_status: dict[str, int] = dict(
        conn.execute("SELECT status, count(*) FROM mgmt_guidance GROUP BY status").fetchall()
    )
    row = conn.execute(
        """
        SELECT
          count(*) FILTER (WHERE method = 'llm' AND reviewed_at IS NOT NULL),
          count(*) FILTER (WHERE method = 'llm' AND status = 'HUMAN_REVIEWED'),
          count(*) FILTER (WHERE method = 'llm' AND pre_review_status = 'QUOTE_VERIFIED'),
          count(*) FILTER (WHERE method = 'llm' AND pre_review_status = 'QUOTE_VERIFIED'
                                                AND status = 'HUMAN_REVIEWED')
        FROM mgmt_guidance
        """
    ).fetchone()
    assert row is not None
    return ReviewStats(by_status, *row)
