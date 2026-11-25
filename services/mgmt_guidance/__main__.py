"""`make guidance ARGS="<command> ..."`: extract, check and review management guidance.

extract: send pending documents to Claude Haiku 5.5 on the Batches API (the
only paid step; budget caps apply). collect: read finished batches. The free
path needs no API key: `pages` prints a document's text and `add` stores a row
you type, after the same quote check.
"""

import argparse
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from services.config import get_settings
from services.db import connect
from services.llm.costs import BudgetExceeded
from services.mgmt_guidance import extract, review
from services.mgmt_guidance.extract import BatchesAPI


def _now() -> datetime:
    return datetime.now(UTC)


def _batches() -> BatchesAPI:
    settings = get_settings()
    key = settings.anthropic_api_key
    if key is None or not key.get_secret_value().strip():
        sys.exit(
            "ANTHROPIC_API_KEY is not set in .env. Extraction is the only paid step; "
            'the free path is `make guidance ARGS="pages --document N"`, then `add`.'
        )
    import anthropic

    client = anthropic.Anthropic(api_key=key.get_secret_value().strip())
    batches: Any = client.messages.batches
    return batches  # type: ignore[no-any-return]


def cmd_extract(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    settings = get_settings()
    isins = [i.upper() for i in a.isin] if a.isin else None
    if a.dry_run:
        r = extract.submit(
            conn, None, settings, now=_now(), isins=isins, limit=a.limit, dry_run=True
        )
        print(f"would send {r.requests} request(s); worst-case cost ${r.estimate_usd:.4f}")
        return
    try:
        r = extract.submit(conn, _batches(), settings, now=_now(), isins=isins, limit=a.limit)
    except BudgetExceeded as exc:
        sys.exit(f"not sent: {exc}")
    if r.batch_id is None:
        print("nothing to extract: every document is done or in flight")
        return
    print(f"batch {r.batch_id}: {r.requests} request(s), worst-case cost ${r.estimate_usd:.4f}")
    print(
        'Collect with `make guidance ARGS="collect --wait"` (most batches finish within an hour).'
    )


def cmd_collect(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    batches = _batches()
    deadline = time.monotonic() + a.timeout_minutes * 60
    while True:
        r = extract.collect(conn, batches, get_settings(), now=_now())
        print(
            f"batches ended {r.batches_ended}, pending {r.batches_pending}; documents "
            f"succeeded {r.succeeded}, failed {r.failed}, refused {r.refused}; rows {r.rows} "
            f"({r.verified} quote-verified); cost ${r.cost_usd:.4f}"
        )
        if not (a.wait and r.batches_pending and time.monotonic() < deadline):
            return
        time.sleep(60)


def cmd_check(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    checked, promoted = extract.recheck(conn)
    print(f"re-checked {checked} flagged row(s); {promoted} now quote-verified")


def cmd_documents(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    rows = conn.execute(
        "SELECT d.id, d.isin, d.doc_type, d.doc_date, d.period_label, d.page_count, "
        "(SELECT count(*) FROM mgmt_guidance g WHERE g.document_id = d.id) "
        "FROM documents d ORDER BY d.doc_date DESC, d.id DESC LIMIT 100"
    ).fetchall()
    for r in rows:
        print(
            f"{r[0]:>5}  {r[1]}  {r[2]:<13} {r[3]}  {r[4] or '-':<8} {r[5]:>3} pages  {r[6]} rows"
        )


def cmd_pages(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    rows = conn.execute(
        "SELECT page_no, text FROM document_pages WHERE document_id = %s ORDER BY page_no",
        (a.document,),
    ).fetchall()
    if not rows:
        sys.exit(f"no document {a.document}")
    for page_no, text in rows:
        print(f"--- page {page_no} ---\n{text}\n")


def cmd_add(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    try:
        gid = review.add_manual(
            conn,
            document_id=a.document,
            metric=a.metric,
            metric_detail=a.detail,
            target_period=a.period,
            target_low=a.low,
            target_high=a.high if a.high is not None else a.low,
            unit=a.unit,
            quote=a.quote,
            note=a.note,
            now=_now(),
        )
    except review.ReviewError as exc:
        sys.exit(f"not stored: {exc}")
    print(f"guidance row {gid} stored as HUMAN_REVIEWED")


def cmd_stats(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    s = review.review_stats(conn)
    print(f"rows by status: {s.by_status or 'none'}")
    if s.agreement is None:
        print("agreement: no quote-verified rows reviewed yet (bar: 90% over 50 rows)")
    else:
        print(
            f"agreement: {s.agreement:.1%} of {s.verified_reviewed} reviewed quote-verified rows "
            "approved (bar: 90% over 50 rows)"
        )
    cost = conn.execute(
        "SELECT coalesce(sum(cost_usd), 0), count(*) FROM llm_usage WHERE purpose = %s",
        (extract.PURPOSE,),
    ).fetchone()
    assert cost is not None
    print(f"extraction cost so far: ${Decimal(cost[0]):.4f} over {cost[1]} request(s)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="make guidance ARGS=", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("extract", help="send pending documents to the Batches API")
    s.add_argument("--isin", action="append")
    s.add_argument("--limit", type=int)
    s.add_argument("--dry-run", action="store_true", help="print the cost estimate only")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("collect", help="read finished batches and quote-check the rows")
    s.add_argument("--wait", action="store_true")
    s.add_argument("--timeout-minutes", type=int, default=90)
    s.set_defaults(func=cmd_collect)

    sub.add_parser("check", help="re-run the quote check on flagged rows").set_defaults(
        func=cmd_check
    )
    sub.add_parser("documents", help="list stored documents").set_defaults(func=cmd_documents)

    s = sub.add_parser("pages", help="print a document's text (for manual entry)")
    s.add_argument("--document", type=int, required=True)
    s.set_defaults(func=cmd_pages)

    s = sub.add_parser("add", help="store a row you typed (free path); the quote is checked")
    s.add_argument("--document", type=int, required=True)
    s.add_argument("--metric", required=True, choices=list(extract.Metric.__args__))  # type: ignore[attr-defined]
    s.add_argument("--detail")
    s.add_argument("--period", required=True, help="target period, such as FY27")
    s.add_argument("--low", type=Decimal, required=True)
    s.add_argument("--high", type=Decimal)
    s.add_argument("--unit", required=True, choices=list(extract.StatedUnit.__args__))  # type: ignore[attr-defined]
    s.add_argument("--quote", required=True, help="copied exactly from the document")
    s.add_argument("--note")
    s.set_defaults(func=cmd_add)

    sub.add_parser("stats", help="status counts, agreement and cost").set_defaults(func=cmd_stats)
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    with connect() as conn:
        conn.autocommit = True
        args.func(conn, args)


if __name__ == "__main__":
    main()
