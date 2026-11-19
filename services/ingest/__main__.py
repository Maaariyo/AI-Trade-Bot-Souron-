"""`make ingest ARGS="<command> ..."`: load data into Postgres.

File-based commands read files the owner downloads; nothing here scrapes an
exchange website. `prices` needs today's Kite login; `news` reads the RSS feeds
in NEWS_FEEDS.
"""

import argparse
import csv
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from services.config import get_settings
from services.db import connect
from services.factors.gates import price_gate_results
from services.ingest import benchmark, corporate_actions, fundamentals, news_cache
from services.ingest import security_master as sm
from services.ingest.kite_auth import make_client
from services.money import ist_date
from services.worker.prices_job import run_prices

log = logging.getLogger("ingest")


def _today() -> date:
    return ist_date(datetime.now(UTC))


def cmd_security_master(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    groups = frozenset(g.strip().upper() for g in a.bse_sme_groups.split(","))
    listings = [
        *sm.parse_nse_list(a.nse, is_sme=False),
        *sm.parse_nse_list(a.nse_sme, is_sme=True),
        *sm.parse_bse_list(a.bse, sme_groups=groups),
    ]
    result = sm.upsert_securities(
        conn, sm.merge_listings(listings), as_of=a.as_of, source="exchange-files"
    )
    c = sm.universe_counts(conn)
    print(
        f"securities: {result.inserted} new, {result.updated} updated, "
        f"{result.marked_delisted} marked delisted"
    )
    print(
        f"active: {c.active_total} (NSE main {c.nse_main}, NSE SME {c.nse_sme}, BSE {c.bse}, "
        f"both {c.both}); suspended {c.suspended}; delisted {c.delisted}"
    )
    print("SPEC expects about 5,470 active equities.")


def cmd_surveillance(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    # GSM first, so a later ASM list cannot downgrade a GSM stock.
    for kind in ("GSM", "ASM"):
        path = getattr(a, kind.lower())
        if path is None:
            continue
        count, unmatched = sm.apply_surveillance(
            conn, kind, sm.parse_surveillance_list(path), as_of=a.as_of, source="exchange-files"
        )
        print(f"{kind}: {count} securities; {len(unmatched)} entries matched no security")


def cmd_actions(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    n = corporate_actions.upsert_actions(
        conn, corporate_actions.parse_actions_csv(a.file), source=a.source
    )
    print(f"corporate actions written: {n}")


def cmd_benchmark(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    n = benchmark.upsert_benchmark(
        conn, benchmark.parse_tri_csv(a.file), is_approximate=False, source=a.source
    )
    print(f"licensed TRI points written: {n}")


def cmd_benchmark_approx(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    rows = conn.execute(
        "SELECT trade_date, close FROM index_prices WHERE index_code = %s ORDER BY trade_date",
        (a.index,),
    ).fetchall()
    with a.yields.open(encoding="utf-8") as f:
        yields = {
            (int(r["year"]), int(r["month"])): Decimal(r["dividend_yield_pct"])
            for r in csv.DictReader(f)
        }
    points = benchmark.approximate_tri([(r[0], r[1]) for r in rows], yields)
    n = benchmark.upsert_benchmark(conn, points, is_approximate=True, source="approx")
    print(f"approximate TRI points written: {n} (labelled approx. TRI)")


def cmd_fundamentals(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    n = fundamentals.upsert_fundamentals(
        conn, fundamentals.parse_fundamentals_csv(a.file), source=a.source
    )
    print(f"fundamental rows written: {n}")


def cmd_prices(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    outcome = run_prices(
        conn,
        get_settings(),
        now=datetime.now(UTC),
        client_factory=lambda s, token: make_client(s, token),
    )
    print(f"prices: {outcome}")
    if outcome == "waiting":
        print("No Kite session today. Log in at http://localhost:8000/kite/login, then rerun.")


def cmd_news(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    feeds = get_settings().news_feeds
    if not feeds:
        sys.exit("NEWS_FEEDS is empty in .env; add publisher RSS URLs first.")
    watch = news_cache.watchlist(conn)
    for url in feeds:
        try:
            items = news_cache.parse_feed(news_cache.fetch_feed(url))
        except Exception as exc:  # one bad feed must not stop the rest
            print(f"{url}: failed ({type(exc).__name__}: {exc})")
            continue
        new, matched = news_cache.store_headlines(conn, items, watch, feed=url)
        print(f"{url}: {len(items)} headlines, {matched} about the watchlist, {new} new")
    print(f"digests built: {news_cache.build_headline_digests(conn, _today())}")


def cmd_gates(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    results = price_gate_results(conn, as_of=a.as_of)
    passed = sum(r.passed for r in results)
    print(f"price gates as of {a.as_of}: {passed} of {len(results)} pass")
    for endpoints in (1, 4):
        calls = fundamentals.monthly_call_budget(passed, endpoints)
        print(f"  fundamentals calls a month at {endpoints} endpoint(s) per stock: {calls:,}")


def cmd_counts(conn: psycopg.Connection[TupleRow], a: argparse.Namespace) -> None:
    print(sm.universe_counts(conn))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="make ingest ARGS=", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("security-master", help="import NSE main, NSE SME and BSE equity lists")
    s.add_argument("--nse", type=Path, required=True)
    s.add_argument("--nse-sme", type=Path, required=True)
    s.add_argument("--bse", type=Path, required=True)
    s.add_argument("--bse-sme-groups", default=",".join(sorted(sm.DEFAULT_BSE_SME_GROUPS)))
    s.set_defaults(func=cmd_security_master)

    s = sub.add_parser("surveillance", help="replace the ASM and/or GSM lists")
    s.add_argument("--gsm", type=Path)
    s.add_argument("--asm", type=Path)
    s.set_defaults(func=cmd_surveillance)

    for name, func, help_text in (
        ("actions", cmd_actions, "corporate actions CSV (project layout)"),
        ("benchmark", cmd_benchmark, "licensed Nifty 500 TRI CSV"),
        ("fundamentals", cmd_fundamentals, "fundamentals CSV (project layout)"),
    ):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("--file", type=Path, required=True)
        s.add_argument("--source", required=True, help="where the file came from")
        s.set_defaults(func=func)

    s = sub.add_parser("benchmark-approx", help="fallback TRI from index prices + yields CSV")
    s.add_argument("--yields", type=Path, required=True, help="year,month,dividend_yield_pct")
    s.add_argument("--index", default="NIFTY 500")
    s.set_defaults(func=cmd_benchmark_approx)

    sub.add_parser("prices", help="run tonight's price update now").set_defaults(func=cmd_prices)
    sub.add_parser("news", help="poll RSS feeds for the watchlist").set_defaults(func=cmd_news)
    sub.add_parser("counts", help="universe counts").set_defaults(func=cmd_counts)
    s = sub.add_parser("gates", help="price-gate pass count and fundamentals call budget")
    s.set_defaults(func=cmd_gates)

    for action in sub.choices.values():
        action.add_argument("--as-of", type=date.fromisoformat, default=_today())
    return p


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = build_parser().parse_args(argv)
    with connect() as conn:
        conn.autocommit = True
        args.func(conn, args)


if __name__ == "__main__":
    main()
