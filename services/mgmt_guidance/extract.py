"""Guidance extraction with Claude Haiku 5.5 on the Message Batches API (Phase 1b).

`submit` sends one request per document (split only if a document would pass
the Haiku prompt ceiling), after the budget check. `collect` reads finished
batches, records cost, validates the JSON, stores rows as EXTRACTED and runs
the quote check. The LLM output is never trusted: only rows that pass the
check, or that the owner approves, can be used (CLAUDE.md rule 10).
"""

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

import psycopg
from psycopg.rows import TupleRow
from pydantic import BaseModel, ConfigDict, ValidationError

from services.config import Settings
from services.llm.costs import Usage, check_budget, cost_usd, record_usage
from services.mgmt_guidance.quote_check import canonical, check_quote

PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_guidance.md"
PURPOSE = "guidance_extraction"
MAX_TOKENS = 16_000
# Haiku 5.5 doubles in price above 100K prompt tokens; stay well under it.
MAX_PROMPT_TOKENS = 80_000
CHARS_PER_TOKEN = 3  # deliberately low, so estimates run high

Metric = Literal[
    "REVENUE",
    "REVENUE_GROWTH",
    "EBITDA",
    "EBITDA_MARGIN",
    "PAT",
    "PAT_GROWTH",
    "CAPEX",
    "NET_DEBT",
    "OTHER",
]
StatedUnit = Literal["percent", "inr_crore", "inr_lakh", "inr", "times"]


class GuidanceRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: Metric
    metric_detail: str
    target_period: str
    target_low: Decimal
    target_high: Decimal
    unit: StatedUnit
    quote: str
    page: int


class ExtractionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[GuidanceRowOut]


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": list(Metric.__args__)},  # type: ignore[attr-defined]
                    "metric_detail": {"type": "string"},
                    "target_period": {"type": "string"},
                    "target_low": {"type": "number"},
                    "target_high": {"type": "number"},
                    "unit": {"type": "string", "enum": list(StatedUnit.__args__)},  # type: ignore[attr-defined]
                    "quote": {"type": "string"},
                    "page": {"type": "integer"},
                },
                "required": [
                    "metric",
                    "metric_detail",
                    "target_period",
                    "target_low",
                    "target_high",
                    "unit",
                    "quote",
                    "page",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
    "additionalProperties": False,
}


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_sha256() -> str:
    material = prompt_text() + json.dumps(SCHEMA, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


class BatchesAPI(Protocol):
    def create(self, *, requests: list[dict[str, Any]]) -> Any: ...

    def retrieve(self, batch_id: str) -> Any: ...

    def results(self, batch_id: str) -> Iterable[Any]: ...


# --- Planning -------------------------------------------------------------------


@dataclass(frozen=True)
class Doc:
    id: int
    isin: str
    company: str
    doc_type: str
    doc_date: date
    period_label: str | None


@dataclass(frozen=True)
class PlannedRequest:
    custom_id: str
    document_id: int
    first_page: int
    last_page: int
    params: dict[str, Any]
    estimate_usd: Decimal


def pending_documents(
    conn: psycopg.Connection[TupleRow], *, isins: list[str] | None = None, limit: int | None = None
) -> list[Doc]:
    """Documents with no extraction that succeeded, was refused, or is in flight."""
    rows = conn.execute(
        """
        SELECT d.id, d.isin, s.name, d.doc_type, d.doc_date, d.period_label
        FROM documents d JOIN securities s USING (isin)
        WHERE NOT EXISTS (
            SELECT 1 FROM extraction_runs r
            WHERE r.document_id = d.id AND r.status IN ('SUBMITTED', 'SUCCEEDED', 'REFUSED'))
          AND (%(isins)s::text[] IS NULL OR d.isin = ANY(%(isins)s::text[]))
        ORDER BY d.doc_date, d.id
        LIMIT %(limit)s
        """,
        {"isins": isins, "limit": limit},
    ).fetchall()
    return [Doc(*r) for r in rows]


def _page_chunks(
    pages: list[tuple[int, str]], budget_chars: int
) -> Iterator[list[tuple[int, str]]]:
    chunk: list[tuple[int, str]] = []
    size = 0
    for page_no, text in pages:
        cost = len(text) + 32
        if chunk and size + cost > budget_chars:
            yield chunk
            chunk, size = [], 0
        chunk.append((page_no, text))
        size += cost
    if chunk:
        yield chunk


def plan_requests(
    conn: psycopg.Connection[TupleRow], settings: Settings, docs: Iterable[Doc]
) -> list[PlannedRequest]:
    system = prompt_text()
    model = settings.models.haiku
    budget_chars = (MAX_PROMPT_TOKENS - len(system) // CHARS_PER_TOKEN - 500) * CHARS_PER_TOKEN
    planned: list[PlannedRequest] = []
    for doc in docs:
        pages = [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT page_no, text FROM document_pages WHERE document_id = %s AND text <> '' "
                "ORDER BY page_no",
                (doc.id,),
            ).fetchall()
        ]
        if not pages:
            continue
        for part, chunk in enumerate(_page_chunks(pages, budget_chars), start=1):
            header = (
                f"Company: {doc.company} (ISIN {doc.isin})\n"
                f"Document: {doc.doc_type.lower().replace('_', ' ')} dated {doc.doc_date:%d %b %Y}"
                + (f", period {doc.period_label}" if doc.period_label else "")
                + "\n\n"
            )
            body = "\n".join(f'<page n="{n}">\n{text}\n</page>' for n, text in chunk)
            user = header + body
            est_input = (len(system) + len(user)) // CHARS_PER_TOKEN
            estimate = cost_usd(
                settings, model, Usage(input_tokens=est_input, output_tokens=MAX_TOKENS), batch=True
            )
            planned.append(
                PlannedRequest(
                    custom_id=f"guidance-doc{doc.id}-part{part}",
                    document_id=doc.id,
                    first_page=chunk[0][0],
                    last_page=chunk[-1][0],
                    params={
                        "model": model,
                        "max_tokens": MAX_TOKENS,
                        "system": [{"type": "text", "text": system}],
                        "messages": [{"role": "user", "content": user}],
                        "output_config": {
                            "effort": settings.effort.guidance_extractor,
                            "format": {"type": "json_schema", "schema": SCHEMA},
                        },
                    },
                    estimate_usd=estimate,
                )
            )
    return planned


# --- Submit -------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitResult:
    requests: int
    estimate_usd: Decimal
    batch_id: str | None


def submit(
    conn: psycopg.Connection[TupleRow],
    batches: BatchesAPI | None,
    settings: Settings,
    *,
    now: datetime,
    isins: list[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> SubmitResult:
    planned = plan_requests(conn, settings, pending_documents(conn, isins=isins, limit=limit))
    estimate = sum((p.estimate_usd for p in planned), Decimal(0))
    if not planned or dry_run:
        return SubmitResult(len(planned), estimate, None)
    if batches is None:
        raise ValueError("a Batches client is needed unless dry_run is set")
    check_budget(conn, settings, estimate, now=now)  # raises before any call
    batch = batches.create(
        requests=[{"custom_id": p.custom_id, "params": p.params} for p in planned]
    )
    digest = prompt_sha256()
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO extraction_runs (document_id, custom_id, batch_id, pages,
                model_requested, prompt_sha256, status, submitted_at)
            VALUES (%s, %s, %s, int4range(%s, %s, '[]'), %s, %s, 'SUBMITTED', %s)
            ON CONFLICT (custom_id) DO UPDATE SET
                batch_id = EXCLUDED.batch_id, status = 'SUBMITTED', error = NULL,
                raw_output = NULL, submitted_at = EXCLUDED.submitted_at, completed_at = NULL
            """,
            [
                (
                    p.document_id,
                    p.custom_id,
                    batch.id,
                    p.first_page,
                    p.last_page,
                    p.params["model"],
                    digest,
                    now,
                )
                for p in planned
            ],
        )
    return SubmitResult(len(planned), estimate, str(batch.id))


# --- Collect --------------------------------------------------------------------------


@dataclass
class CollectResult:
    batches_ended: int = 0
    batches_pending: int = 0
    succeeded: int = 0
    failed: int = 0
    refused: int = 0
    rows: int = 0
    verified: int = 0
    cost_usd: Decimal = Decimal(0)
    errors: list[str] = field(default_factory=list)


def _finish(
    conn: psycopg.Connection[TupleRow],
    custom_id: str,
    status: str,
    *,
    now: datetime,
    model_served: str | None = None,
    stop_reason: str | None = None,
    raw: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE extraction_runs SET status = %s, model_served = %s, stop_reason = %s,
            raw_output = %s, error = %s, completed_at = %s
        WHERE custom_id = %s
        """,
        (status, model_served, stop_reason, raw, error, now, custom_id),
    )


def insert_rows(
    conn: psycopg.Connection[TupleRow], run_id: int, document_id: int, rows: list[GuidanceRowOut]
) -> tuple[int, int]:
    """Store rows as EXTRACTED or QUOTE_VERIFIED. Returns (rows, verified)."""
    doc = conn.execute(
        "SELECT isin, doc_date FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    assert doc is not None
    pages = [
        r[0]
        for r in conn.execute(
            "SELECT text FROM document_pages WHERE document_id = %s ORDER BY page_no",
            (document_id,),
        ).fetchall()
    ]
    verified = 0
    for r in rows:
        low, high = sorted((r.target_low, r.target_high))
        result = check_quote(r.quote, pages, sorted({low, high}), claimed_page=r.page)
        status = "QUOTE_VERIFIED" if result.verified else "EXTRACTED"
        verified += result.verified
        c_low, unit = canonical(low, r.unit)
        c_high, _ = canonical(high, r.unit)
        conn.execute(
            """
            INSERT INTO mgmt_guidance (isin, document_id, extraction_run_id, method, stated_on,
                metric, metric_detail, target_period, target_low_stated, target_high_stated,
                unit_stated, target_low, target_high, unit, quote, page_no, status, flag)
            VALUES (%s, %s, %s, 'llm', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                doc[0],
                document_id,
                run_id,
                doc[1],
                r.metric,
                r.metric_detail or None,
                r.target_period,
                low,
                high,
                r.unit,
                c_low,
                c_high,
                unit,
                r.quote,
                result.page_no,
                status,
                result.flag,
            ),
        )
    return len(rows), verified


def collect(
    conn: psycopg.Connection[TupleRow], batches: BatchesAPI, settings: Settings, *, now: datetime
) -> CollectResult:
    out = CollectResult()
    batch_ids = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT batch_id FROM extraction_runs "
            "WHERE status = 'SUBMITTED' AND batch_id IS NOT NULL"
        ).fetchall()
    ]
    for batch_id in batch_ids:
        if batches.retrieve(batch_id).processing_status != "ended":
            out.batches_pending += 1
            continue
        out.batches_ended += 1
        runs = {
            r[0]: (r[1], r[2], r[3])
            for r in conn.execute(
                "SELECT custom_id, id, document_id, model_requested FROM extraction_runs "
                "WHERE batch_id = %s AND status = 'SUBMITTED'",
                (batch_id,),
            ).fetchall()
        }
        for result in batches.results(batch_id):
            if result.custom_id not in runs:
                continue
            run_id, document_id, model_requested = runs[result.custom_id]
            kind = result.result.type
            with conn.transaction():
                if kind != "succeeded":
                    error = getattr(getattr(result.result, "error", None), "type", None) or kind
                    _finish(conn, result.custom_id, "FAILED", now=now, error=str(error))
                    out.failed += 1
                    continue
                msg = result.result.message
                usage = msg.usage
                out.cost_usd += record_usage(
                    conn,
                    settings,
                    purpose=PURPOSE,
                    request_ref=result.custom_id,
                    model_requested=model_requested,
                    model_served=msg.model,
                    usage=Usage(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    ),
                    batch=True,
                    at=now,
                )
                text = next((b.text for b in msg.content if b.type == "text"), "")
                common = {"now": now, "model_served": msg.model, "stop_reason": msg.stop_reason}
                if msg.stop_reason == "refusal":
                    _finish(conn, result.custom_id, "REFUSED", raw=text, **common)
                    out.refused += 1
                    continue
                if msg.stop_reason == "max_tokens":
                    _finish(
                        conn,
                        result.custom_id,
                        "FAILED",
                        raw=text,
                        error="output cut off at max_tokens",
                        **common,
                    )
                    out.failed += 1
                    continue
                try:
                    parsed = ExtractionOut.model_validate_json(text)
                except ValidationError as exc:
                    _finish(
                        conn,
                        result.custom_id,
                        "FAILED",
                        raw=text,
                        error=f"invalid JSON: {exc.error_count()} errors",
                        **common,
                    )
                    out.failed += 1
                    out.errors.append(result.custom_id)
                    continue
                n, v = insert_rows(conn, run_id, document_id, parsed.rows)
                _finish(conn, result.custom_id, "SUCCEEDED", raw=text, **common)
                out.succeeded += 1
                out.rows += n
                out.verified += v
    return out


def recheck(conn: psycopg.Connection[TupleRow]) -> tuple[int, int]:
    """Re-run the quote check on every EXTRACTED llm row. Returns (checked, now verified)."""
    rows = conn.execute(
        "SELECT id, document_id, quote, target_low_stated, target_high_stated, page_no "
        "FROM mgmt_guidance WHERE status = 'EXTRACTED' AND method = 'llm'"
    ).fetchall()
    promoted = 0
    with conn.transaction():
        for gid, doc_id, quote, low, high, page in rows:
            pages = [
                r[0]
                for r in conn.execute(
                    "SELECT text FROM document_pages WHERE document_id = %s ORDER BY page_no",
                    (doc_id,),
                ).fetchall()
            ]
            res = check_quote(quote, pages, sorted({low, high}), claimed_page=page)
            conn.execute(
                "UPDATE mgmt_guidance SET status = %s, flag = %s, page_no = %s WHERE id = %s",
                ("QUOTE_VERIFIED" if res.verified else "EXTRACTED", res.flag, res.page_no, gid),
            )
            promoted += res.verified
    return len(rows), promoted
