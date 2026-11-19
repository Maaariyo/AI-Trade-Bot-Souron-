"""The Nifty 500 TRI benchmark (SPEC section 4).

Preferred: a licensed TRI series, imported from a file the owner downloads
(for example from NSE Indices). Fallback, used only when no licensed TRI
exists: the Nifty 500 price index plus the published index dividend yield
divided by 12, applied on the first trading day of each month. Fallback rows
carry is_approximate = true and the UI labels them "approx. TRI".
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import TupleRow

from services.ingest.csvfiles import parse_date, read_rows

CODE = "NIFTY500_TRI"
METHOD_LICENSED = "licensed_tri"
METHOD_APPROX = "price_index_plus_dividend_yield_div_12"

_TRI_ALIASES = {
    "date": ("DATE", "HISTORICALDATE", "INDEXDATE"),
    "value": ("TOTALRETURNSINDEX", "TOTALRETURNINDEX", "TRI", "CLOSE", "VALUE"),
}


@dataclass(frozen=True)
class BenchmarkPoint:
    trade_date: date
    value: Decimal


def parse_tri_csv(source: Path | str) -> list[BenchmarkPoint]:
    points: list[BenchmarkPoint] = []
    for r in read_rows(source, _TRI_ALIASES, {"date", "value"}):
        day = parse_date(r["date"])
        if day is None or not r["value"]:
            continue
        points.append(BenchmarkPoint(day, Decimal(r["value"].replace(",", ""))))
    return sorted(points, key=lambda p: p.trade_date)


def approximate_tri(
    price_index: Sequence[tuple[date, Decimal]],
    dividend_yield_pct: Mapping[tuple[int, int], Decimal],
    *,
    base: Decimal | None = None,
) -> list[BenchmarkPoint]:
    """Price-index returns, plus yield/12 on each month's first trading day.

    `dividend_yield_pct` maps (year, month) to the published annual yield in
    percent. A month with no published yield adds nothing for that month.
    """
    out: list[BenchmarkPoint] = []
    level: Decimal | None = base
    prev_close: Decimal | None = None
    prev_month: tuple[int, int] | None = None
    for day, close in price_index:
        month = (day.year, day.month)
        if level is None or prev_close is None:
            level = level if level is not None else close
        else:
            level *= close / prev_close
            if month != prev_month:
                level *= 1 + dividend_yield_pct.get(month, Decimal(0)) / 100 / 12
        out.append(BenchmarkPoint(day, level.quantize(Decimal("0.0001"))))
        prev_close, prev_month = close, month
    return out


def upsert_benchmark(
    conn: psycopg.Connection[TupleRow],
    points: Iterable[BenchmarkPoint],
    *,
    is_approximate: bool,
    source: str,
    code: str = CODE,
) -> int:
    """Write points. A licensed value is never overwritten by an approximate one."""
    method = METHOD_APPROX if is_approximate else METHOD_LICENSED
    params = [(code, p.trade_date, p.value, is_approximate, method, source) for p in points]
    if not params:
        return 0
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO benchmark_values
                (code, trade_date, value, is_approximate, method, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (code, trade_date) DO UPDATE SET
                value = EXCLUDED.value,
                is_approximate = EXCLUDED.is_approximate,
                method = EXCLUDED.method,
                source = EXCLUDED.source,
                ingested_at = now()
            WHERE benchmark_values.is_approximate OR NOT EXCLUDED.is_approximate
            """,
            params,
        )
    return len(params)
