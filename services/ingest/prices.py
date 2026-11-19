"""Daily candles from Kite Connect into daily_prices.

One instrument per ISIN: NSE when the company is listed there, else BSE.
Requests are rate-limited, ranges are chunked, and writes are idempotent
upserts, so a run can stop and restart at any point.
"""

import logging
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import psycopg
from psycopg.rows import TupleRow

from services.ingest.kite_auth import BROKER, KiteClient
from services.money import ist_date, to_paise

log = logging.getLogger(__name__)

SOURCE = "kite"


@dataclass(frozen=True)
class Candle:
    trade_date: date
    open_paise: int
    high_paise: int
    low_paise: int
    close_paise: int
    volume: int

    def is_valid(self) -> bool:
        lo, hi = self.low_paise, self.high_paise
        return (
            min(self.open_paise, hi, lo, self.close_paise) > 0
            and lo <= hi
            and lo <= self.open_paise <= hi
            and lo <= self.close_paise <= hi
            and self.volume >= 0
        )

    @property
    def estimated_value_paise(self) -> int:
        """Typical price times volume. Kite day candles carry no traded value."""
        typical = (self.high_paise + self.low_paise + self.close_paise) // 3
        return typical * self.volume


def candles_from_kite(rows: Iterable[dict[str, Any]]) -> list[Candle]:
    return [
        Candle(
            trade_date=ist_date(r["date"]),
            open_paise=to_paise(r["open"]),
            high_paise=to_paise(r["high"]),
            low_paise=to_paise(r["low"]),
            close_paise=to_paise(r["close"]),
            volume=int(r["volume"]),
        )
        for r in rows
    ]


class RateLimiter:
    """Spaces calls at least 1/rate seconds apart."""

    def __init__(
        self,
        per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / per_second
        self._clock, self._sleep = clock, sleep
        self._next = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self._interval


def years_before(day: date, years: int) -> date:
    """The same calendar day `years` earlier; 29 Feb becomes 28 Feb."""
    return date(day.year - years, day.month, min(day.day, 28) if day.month == 2 else day.day)


def date_chunks(start: date, end: date, max_days: int) -> Iterator[tuple[date, date]]:
    """Inclusive [from, to] ranges of at most max_days days."""
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=max_days - 1))
        yield cur, stop
        cur = stop + timedelta(days=1)


# --- Instruments --------------------------------------------------------------


@dataclass(frozen=True)
class MappingResult:
    instruments: int
    mapped: int


def refresh_instruments(
    conn: psycopg.Connection[TupleRow], client: KiteClient, *, as_of: date
) -> MappingResult:
    """Store Kite's NSE and BSE equity instruments and map them to ISINs.

    Kite's instrument dump has no ISIN column, so the mapping uses the
    security master: NSE by trading symbol (ignoring a "-BE"-style series
    suffix), BSE by exchange token, which is the BSE scrip code.
    """
    rows: list[dict[str, Any]] = []
    for exchange in ("NSE", "BSE"):
        rows += [
            r
            for r in client.instruments(exchange)
            if (r.get("instrument_type") == "EQ" and r.get("segment") == exchange)
            or r.get("segment") == "INDICES"
        ]
    with conn.transaction():
        nse: dict[str, str] = dict(
            conn.execute(
                "SELECT nse_symbol, isin FROM securities "
                "WHERE nse_symbol IS NOT NULL AND status <> 'DELISTED'"
            ).fetchall()
        )
        bse: dict[str, str] = dict(
            conn.execute(
                "SELECT bse_code, isin FROM securities "
                "WHERE bse_code IS NOT NULL AND status <> 'DELISTED'"
            ).fetchall()
        )
        mapped = 0
        with conn.cursor() as cur:
            params = []
            for r in rows:
                symbol = str(r["tradingsymbol"])
                if r.get("segment") == "INDICES":
                    isin = None
                elif r["exchange"] == "NSE":
                    isin = nse.get(symbol) or nse.get(symbol.rsplit("-", 1)[0])
                else:
                    isin = bse.get(str(r["exchange_token"]))
                mapped += isin is not None
                params.append(
                    (
                        BROKER,
                        r["exchange"],
                        int(r["instrument_token"]),
                        str(r["exchange_token"]),
                        symbol,
                        r.get("name"),
                        r.get("instrument_type"),
                        r.get("segment"),
                        isin,
                        as_of,
                    )
                )
            cur.executemany(
                """
                INSERT INTO broker_instruments (broker, exchange, instrument_token, exchange_token,
                    tradingsymbol, name, instrument_type, segment, isin, as_of)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (broker, exchange, instrument_token) DO UPDATE SET
                    exchange_token = EXCLUDED.exchange_token,
                    tradingsymbol = EXCLUDED.tradingsymbol,
                    name = EXCLUDED.name,
                    isin = EXCLUDED.isin,
                    as_of = EXCLUDED.as_of
                """,
                params,
            )
    return MappingResult(instruments=len(rows), mapped=mapped)


@dataclass(frozen=True)
class Target:
    isin: str
    exchange: str
    instrument_token: int
    last_date: date | None
    last_close_paise: int | None = None


def price_targets(conn: psycopg.Connection[TupleRow], *, as_of: date) -> list[Target]:
    """Active securities with a current Kite instrument, NSE preferred."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (s.isin) s.isin, bi.exchange, bi.instrument_token,
               last.trade_date, last.close_paise
        FROM securities s
        JOIN broker_instruments bi ON bi.isin = s.isin AND bi.broker = %s AND bi.as_of = %s
        LEFT JOIN LATERAL (
            SELECT trade_date, close_paise FROM daily_prices dp
            WHERE dp.isin = s.isin AND dp.exchange = bi.exchange
            ORDER BY trade_date DESC LIMIT 1
        ) last ON true
        WHERE s.status = 'ACTIVE'
        ORDER BY s.isin, bi.exchange = 'NSE' DESC
        """,
        (BROKER, as_of),
    ).fetchall()
    return [Target(r[0], r[1], r[2], r[3], r[4]) for r in rows]


# --- Candles --------------------------------------------------------------------


def upsert_candles(
    conn: psycopg.Connection[TupleRow], isin: str, exchange: str, candles: Iterable[Candle]
) -> int:
    params = [
        (
            isin,
            exchange,
            c.trade_date,
            c.open_paise,
            c.high_paise,
            c.low_paise,
            c.close_paise,
            c.volume,
            c.estimated_value_paise,
            SOURCE,
        )
        for c in candles
    ]
    if not params:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO daily_prices (isin, exchange, trade_date, open_paise, high_paise,
                low_paise, close_paise, volume, traded_value_paise, value_is_estimate, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s)
            ON CONFLICT (isin, exchange, trade_date) DO UPDATE SET
                open_paise = EXCLUDED.open_paise,
                high_paise = EXCLUDED.high_paise,
                low_paise = EXCLUDED.low_paise,
                close_paise = EXCLUDED.close_paise,
                volume = EXCLUDED.volume,
                traded_value_paise = EXCLUDED.traded_value_paise,
                source = EXCLUDED.source,
                ingested_at = now()
            """,
            params,
        )
    return len(params)


@dataclass
class IngestResult:
    targets: int = 0
    requests: int = 0
    rows: int = 0
    invalid_candles: int = 0
    rebased: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)


# Kite re-adjusts past candles after splits and bonuses. If the overlap day's
# close moved by more than this, the stored history is stale and is re-fetched.
REBASE_TOLERANCE = 0.002


def ingest_daily_prices(
    conn: psycopg.Connection[TupleRow],
    client: KiteClient,
    targets: Iterable[Target],
    *,
    today: date,
    history_years: int,
    max_days_per_request: int,
    limiter: RateLimiter,
) -> IngestResult:
    """Fetch candles from each target's last stored date (or N years back) to today.

    Incremental fetches start at the last stored date, so one candle overlaps.
    Kite rewrites past candles after a split or bonus; if the overlap close no
    longer matches, the target's whole history is fetched again and overwritten.

    A Kite TokenException stops the run: the session is gone and every later
    call would fail. Other per-instrument errors are recorded and skipped.
    """
    from kiteconnect import exceptions as kex

    result = IngestResult()
    earliest = years_before(today, history_years)

    def fetch(t: Target, start: date) -> list[Candle]:
        out: list[Candle] = []
        for frm, to in date_chunks(start, today, max_days_per_request):
            limiter.wait()
            result.requests += 1
            out += candles_from_kite(client.historical_data(t.instrument_token, frm, to, "day"))
        return out

    for t in targets:
        result.targets += 1
        try:
            candles = fetch(t, t.last_date or earliest)
            if t.last_date and t.last_close_paise:
                overlap = next((c for c in candles if c.trade_date == t.last_date), None)
                moved = (
                    overlap is not None
                    and abs(overlap.close_paise - t.last_close_paise) / t.last_close_paise
                    > REBASE_TOLERANCE
                )
                if moved:
                    result.rebased.append(t.isin)
                    log.info("history re-adjusted upstream for %s; re-fetching", t.isin)
                    candles = fetch(t, earliest)
            valid = [c for c in candles if c.is_valid()]
            result.invalid_candles += len(candles) - len(valid)
            with conn.transaction():
                result.rows += upsert_candles(conn, t.isin, t.exchange, valid)
        except kex.TokenException:
            raise
        except (kex.KiteException, ValueError) as exc:
            result.failures[t.isin] = f"{type(exc).__name__}: {exc}"
            log.warning("prices failed for %s: %s", t.isin, exc)
    return result


# --- Index candles ----------------------------------------------------------------


def ingest_index_prices(
    conn: psycopg.Connection[TupleRow],
    client: KiteClient,
    index_codes: Iterable[str],
    *,
    as_of: date,
    today: date,
    history_years: int,
    max_days_per_request: int,
    limiter: RateLimiter,
) -> tuple[int, list[str]]:
    """Index candles into index_prices. Returns (rows written, codes not found)."""
    found: dict[str, int] = dict(
        conn.execute(
            "SELECT tradingsymbol, instrument_token FROM broker_instruments "
            "WHERE broker = %s AND segment = 'INDICES' AND as_of = %s",
            (BROKER, as_of),
        ).fetchall()
    )
    rows = 0
    missing: list[str] = []
    for code in index_codes:
        token = found.get(code)
        if token is None:
            missing.append(code)
            continue
        last = conn.execute(
            "SELECT max(trade_date) FROM index_prices WHERE index_code = %s", (code,)
        ).fetchone()
        start = (
            (last[0] + timedelta(days=1))
            if last and last[0]
            else years_before(today, history_years)
        )
        for frm, to in date_chunks(start, today, max_days_per_request):
            limiter.wait()
            data = client.historical_data(token, frm, to, "day")
            params = [
                (code, ist_date(r["date"]), r["open"], r["high"], r["low"], r["close"], SOURCE)
                for r in data
            ]
            if params:
                with conn.transaction(), conn.cursor() as cur:
                    cur.executemany(
                        """
                        INSERT INTO index_prices
                            (index_code, trade_date, open, high, low, close, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (index_code, trade_date) DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                            close = EXCLUDED.close, ingested_at = now()
                        """,
                        params,
                    )
                rows += len(params)
    return rows, missing
