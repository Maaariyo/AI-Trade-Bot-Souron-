"""Filings: results, board meetings, pledges, auditor changes, rating actions.

The SPEC sources these from the fundamentals vendor's feed, so the adapter
arrives with the vendor decision (D1). This module holds the record type, the
adapter interface and storage. Agents later web-fetch one filing URL at a time.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import psycopg
from psycopg.rows import TupleRow


@dataclass(frozen=True)
class Filing:
    isin: str
    filed_at: datetime
    category: str
    title: str
    url: str
    summary: str | None = None

    def __post_init__(self) -> None:
        if self.filed_at.tzinfo is None:
            raise ValueError(f"{self.isin}: filed_at needs a time zone")
        if not self.url.startswith("https://"):
            raise ValueError(f"{self.isin}: filing URL must be https: {self.url}")


class FilingsSource(Protocol):
    name: str

    def fetch_since(self, since: datetime, isins: Iterable[str]) -> Iterable[Filing]: ...


def upsert_filings(
    conn: psycopg.Connection[TupleRow], filings: Iterable[Filing], *, source: str
) -> int:
    params = [(f.isin, f.filed_at, f.category, f.title, f.url, f.summary, source) for f in filings]
    if not params:
        return 0
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO filings (isin, filed_at, category, title, url, summary, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, url) DO UPDATE SET
                category = EXCLUDED.category,
                title = EXCLUDED.title,
                summary = COALESCE(EXCLUDED.summary, filings.summary)
            """,
            params,
        )
    return len(params)
