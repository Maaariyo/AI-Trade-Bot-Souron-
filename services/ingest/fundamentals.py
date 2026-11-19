"""Point-in-time fundamentals (SPEC section 5).

Every row needs `available_from`: the moment the figure became public. A
restatement is a new row with a later available_from, and reads as of a date
only see rows already public then. Fundamentals are pulled only for stocks
that pass the price gates (services/factors/gates.py).

Until a vendor adapter exists (decision D1), rows load from a CSV in this
project's own layout:

    isin,period_end,period_type,statement,field,value,unit,available_from

Money values are in rupees in the file and stored as paise.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import ceil
from pathlib import Path
from typing import Literal, Protocol

import psycopg
from psycopg.rows import TupleRow

from services.ingest.csvfiles import parse_date, read_rows

PeriodType = Literal["Q", "H", "FY", "TTM"]
Statement = Literal["PL", "BS", "CF", "RATIO", "SHAREHOLDING"]
Unit = Literal["paise", "ratio", "percent", "count", "shares", "days"]

REFRESHES_PER_MONTH = 4.3


@dataclass(frozen=True)
class FundamentalRow:
    isin: str
    period_end: date
    period_type: PeriodType
    statement: Statement
    field: str
    value: Decimal
    unit: Unit
    available_from: datetime

    def __post_init__(self) -> None:
        if self.available_from.tzinfo is None:
            raise ValueError(f"{self.isin} {self.field}: available_from needs a time zone")
        if self.available_from.date() < self.period_end:
            raise ValueError(
                f"{self.isin} {self.field}: available_from {self.available_from:%Y-%m-%d} "
                f"is before period end {self.period_end}"
            )


class FundamentalsSource(Protocol):
    """A vendor adapter. One is written once the owner picks a vendor (D1)."""

    name: str
    endpoints_per_stock: int

    def fetch(self, isins: Iterable[str]) -> Iterable[FundamentalRow]: ...


def monthly_call_budget(
    stocks: int, endpoints_per_stock: int, refreshes_per_month: float = REFRESHES_PER_MONTH
) -> int:
    """Vendor API calls a month for weekly refreshes (SPEC section 5)."""
    return ceil(stocks * endpoints_per_stock * refreshes_per_month)


_ALIASES = {
    "isin": ("ISIN",),
    "period_end": ("PERIODEND",),
    "period_type": ("PERIODTYPE",),
    "statement": ("STATEMENT",),
    "field": ("FIELD",),
    "value": ("VALUE",),
    "unit": ("UNIT",),
    "available_from": ("AVAILABLEFROM",),
}


def parse_fundamentals_csv(source: Path | str) -> list[FundamentalRow]:
    out: list[FundamentalRow] = []
    for r in read_rows(source, _ALIASES, set(_ALIASES)):
        period_end = parse_date(r["period_end"])
        if period_end is None:
            raise ValueError(f"{r['isin']} {r['field']}: missing period_end")
        unit = r["unit"].lower()
        value = Decimal(r["value"].replace(",", ""))
        if unit in ("rupees", "inr"):
            unit, value = "paise", value * 100
        out.append(
            FundamentalRow(
                isin=r["isin"].upper(),
                period_end=period_end,
                period_type=r["period_type"].upper(),  # type: ignore[arg-type]
                statement=r["statement"].upper(),  # type: ignore[arg-type]
                field=r["field"],
                value=value,
                unit=unit,  # type: ignore[arg-type]
                available_from=datetime.fromisoformat(r["available_from"]),
            )
        )
    return out


def upsert_fundamentals(
    conn: psycopg.Connection[TupleRow], rows: Iterable[FundamentalRow], *, source: str
) -> int:
    params = [
        (
            r.isin,
            r.period_end,
            r.period_type,
            r.statement,
            r.field,
            r.value,
            r.unit,
            r.available_from,
            source,
        )
        for r in rows
    ]
    if not params:
        return 0
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO fundamentals (isin, period_end, period_type, statement, field, value,
                unit, available_from, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (isin, period_end, period_type, statement, field, source, available_from)
            DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, ingested_at = now()
            """,
            params,
        )
    return len(params)


@dataclass(frozen=True)
class PointInTimeValue:
    period_end: date
    period_type: str
    statement: str
    field: str
    value: Decimal
    unit: str
    available_from: datetime


def fundamentals_as_of(
    conn: psycopg.Connection[TupleRow], isin: str, as_of: datetime
) -> list[PointInTimeValue]:
    """The latest public version of each figure as of `as_of` (available_from <= as_of)."""
    if as_of.tzinfo is None:
        raise ValueError("as_of needs a time zone")
    rows = conn.execute(
        """
        SELECT DISTINCT ON (period_end, period_type, statement, field)
               period_end, period_type, statement, field, value, unit, available_from
        FROM fundamentals
        WHERE isin = %s AND available_from <= %s
        ORDER BY period_end, period_type, statement, field, available_from DESC
        """,
        (isin, as_of),
    ).fetchall()
    return [PointInTimeValue(*r) for r in rows]
