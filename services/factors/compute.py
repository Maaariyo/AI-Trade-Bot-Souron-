"""Raw factor values for one as_of date (SPEC section 5), written as a screen run.

Point in time (CLAUDE.md rule 4): a fundamental row is used only if its
available_from is before the end of the as_of day (IST), and a historical P/E
uses only the rows public at that month-end. Prices are read up to as_of.

Factor formulas are documented in definitions.yaml; units follow the
canonical fields there (money in paise, percentages in percent).
"""

import math
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from itertools import pairwise

import numpy as np
import numpy.typing as npt
import psycopg
from psycopg.rows import TupleRow

from services.factors.definitions import Definitions, load_definitions
from services.factors.engine import StockInput
from services.money import IST

PRICE_WINDOW_DAYS = 400  # enough for 253 trading days
GATE_LOOKBACK_DAYS = 91
BENCHMARK_INDEX = "NIFTY 500"
FloatArray = npt.NDArray[np.float64]


def cutoff(as_of: date) -> datetime:
    """End of the as_of day in IST: rows public before this may be used."""
    return datetime.combine(as_of + timedelta(days=1), time(0, 0), tzinfo=IST)


# --- Point-in-time fundamentals ---------------------------------------------------------


@dataclass
class PitFundamentals:
    """One stock's fundamentals: (field, period_type) -> period_end -> [(available_from, value)]."""

    rows: dict[tuple[str, str], dict[date, list[tuple[datetime, float]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )

    def add(self, fld: str, ptype: str, period_end: date, avail: datetime, value: float) -> None:
        self.rows[(fld, ptype)][period_end].append((avail, value))

    def series(self, fld: str, ptype: str, as_of: datetime) -> list[tuple[date, float]]:
        """Each period's latest version public by `as_of`, oldest period first."""
        out: list[tuple[date, float]] = []
        for period_end, versions in sorted(self.rows.get((fld, ptype), {}).items()):
            public = [v for v in versions if v[0] <= as_of]
            if public:
                out.append((period_end, max(public)[1]))
        return out

    def latest(self, fld: str, ptype: str, as_of: datetime) -> tuple[date, float] | None:
        s = self.series(fld, ptype, as_of)
        return s[-1] if s else None

    def latest_any(self, fld: str, as_of: datetime) -> tuple[date, float] | None:
        found = [x for p in ("Q", "H", "FY", "TTM") if (x := self.latest(fld, p, as_of))]
        return max(found) if found else None

    def at_period(self, fld: str, ptype: str, period_end: date, as_of: datetime) -> float | None:
        return dict(self.series(fld, ptype, as_of)).get(period_end)


def consecutive_quarters(series: list[tuple[date, float]], n: int) -> list[float] | None:
    """The last n quarterly values if they are consecutive quarters, else None."""
    if len(series) < n:
        return None
    tail = series[-n:]
    for (a, _), (b, _) in pairwise(tail):
        if not 80 <= (b - a).days <= 100:
            return None
    return [v for _, v in tail]


def ttm(pit: PitFundamentals, fld: str, as_of: datetime, *, offset: int = 0) -> float | None:
    """Sum of 4 consecutive quarters; offset=4 gives the TTM a year earlier."""
    s = pit.series(fld, "Q", as_of)
    if offset:
        s = s[:-offset] if len(s) > offset else []
    q = consecutive_quarters(s, 4)
    return sum(q) if q else None


def load_fundamentals(
    conn: psycopg.Connection[TupleRow], as_of: date, fields: Iterable[str]
) -> dict[str, PitFundamentals]:
    out: dict[str, PitFundamentals] = defaultdict(PitFundamentals)
    rows = conn.execute(
        "SELECT isin, field, period_type, period_end, available_from, value FROM fundamentals "
        "WHERE available_from < %s AND field = ANY(%s)",
        (cutoff(as_of), list(fields)),
    )
    for isin, fld, ptype, period_end, avail, value in rows:
        out[isin].add(fld, ptype, period_end, avail, float(value))
    return out


# --- Prices -------------------------------------------------------------------------------


@dataclass
class PriceSeries:
    dates: list[date]
    closes: FloatArray  # paise
    values: list[int | None]  # traded value, paise


def load_prices(conn: psycopg.Connection[TupleRow], as_of: date) -> dict[str, PriceSeries]:
    rows = conn.execute(
        """
        SELECT DISTINCT ON (isin, trade_date) isin, trade_date, close_paise, traded_value_paise
        FROM daily_prices
        WHERE trade_date > %s AND trade_date <= %s
        ORDER BY isin, trade_date, exchange = 'NSE' DESC
        """,
        (as_of - timedelta(days=PRICE_WINDOW_DAYS), as_of),
    ).fetchall()
    grouped: dict[str, tuple[list[date], list[float], list[int | None]]] = defaultdict(
        lambda: ([], [], [])
    )
    for isin, d, close, value in rows:
        g = grouped[isin]
        g[0].append(d)
        g[1].append(float(close))
        g[2].append(value)
    return {k: PriceSeries(v[0], np.array(v[1]), v[2]) for k, v in grouped.items()}


def load_index(conn: psycopg.Connection[TupleRow], as_of: date) -> dict[date, float]:
    rows = conn.execute(
        "SELECT trade_date, close FROM index_prices WHERE index_code = %s "
        "AND trade_date > %s AND trade_date <= %s",
        (BENCHMARK_INDEX, as_of - timedelta(days=PRICE_WINDOW_DAYS), as_of),
    ).fetchall()
    return {d: float(c) for d, c in rows}


def load_month_end_closes(
    conn: psycopg.Connection[TupleRow], as_of: date
) -> dict[str, list[tuple[date, float]]]:
    rows = conn.execute(
        """
        SELECT DISTINCT ON (isin, date_trunc('month', trade_date)) isin, trade_date, close_paise
        FROM daily_prices
        WHERE trade_date > %s AND trade_date <= %s
        ORDER BY isin, date_trunc('month', trade_date), trade_date DESC, exchange = 'NSE' DESC
        """,
        (as_of - timedelta(days=5 * 366), as_of),
    ).fetchall()
    out: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for isin, d, close in rows:
        out[isin].append((d, float(close)))
    return out


def price_factors(p: PriceSeries, index: dict[date, float]) -> dict[str, float]:
    c = p.closes
    out: dict[str, float] = {}
    n = c.size
    if n >= 253:
        out["mom_12_1"] = (c[-22] / c[-253] - 1) * 100
        ret_12m = c[-1] / c[-253] - 1
        start, end = p.dates[-253], p.dates[-1]
        if start in index and end in index:
            out["rel_strength_12m"] = (ret_12m - (index[end] / index[start] - 1)) * 100
    if n >= 200:
        out["price_vs_200dma"] = (c[-1] / c[-200:].mean() - 1) * 100
    window = c[-253:]
    if window.size >= 201:
        logret = np.diff(np.log(window))
        out["vol_1y"] = float(logret.std(ddof=1) * math.sqrt(252) * 100)
        peak = np.maximum.accumulate(window)
        out["max_drawdown_1y"] = float(((peak - window) / peak).max() * 100)
        days = p.dates[-window.size :]
        if all(d in index for d in days):
            m = np.array([index[d] for d in days])
            sret, mret = np.diff(window) / window[:-1], np.diff(m) / m[:-1]
            var = mret.var(ddof=1)
            if var > 0:
                out["beta_1y"] = float(np.cov(sret, mret, ddof=1)[0, 1] / var)
    return out


# --- Fundamental factors -----------------------------------------------------------------


def _ratio(a: float | None, b: float | None, *, positive_b: bool = True) -> float | None:
    if a is None or b is None or b == 0 or (positive_b and b < 0):
        return None
    return a / b


def _cagr(series: list[tuple[date, float]], years: int = 3) -> float | None:
    if not series:
        return None
    end_date, end_val = series[-1]
    start = next(
        (v for d, v in series if d.year == end_date.year - years and d.month == end_date.month),
        None,
    )
    if start is None or start <= 0 or end_val <= 0:
        return None
    growth: float = (end_val / start) ** (1 / years) - 1
    return growth * 100


def fundamental_factors(
    pit: PitFundamentals,
    *,
    as_of: date,
    close_paise: float | None,
    month_end_closes: list[tuple[date, float]],
) -> tuple[dict[str, float], int | None, int]:
    """(factor values, market cap in paise, quarters of results available)."""
    now = cutoff(as_of)
    out: dict[str, float | None] = {}
    shares = pit.latest_any("shares_outstanding", now)
    mcap = close_paise * shares[1] if close_paise and shares and shares[1] > 0 else None
    quarters = len(pit.series("revenue", "Q", now)) or len(pit.series("pat", "Q", now))

    # Value
    eps_ttm = ttm(pit, "eps", now)
    pe_now = _ratio(close_paise, eps_ttm)
    history: list[float] = []
    for month_end, close in month_end_closes[-60:]:
        e = ttm(pit, "eps", cutoff(month_end))
        if e and e > 0:
            history.append(close / e)
    if pe_now is not None and len(history) >= 24:
        out["pe_vs_median"] = pe_now / statistics.median(history)
    debt = pit.latest("total_debt", "FY", now)
    cash = pit.latest("cash", "FY", now)
    equity = pit.latest("equity", "FY", now) or pit.latest_any("equity", now)
    ebitda_ttm = ttm(pit, "ebitda", now)
    if mcap is not None and debt and cash and ebitda_ttm and ebitda_ttm > 0:
        out["ev_ebitda"] = (mcap + debt[1] - cash[1]) / ebitda_ttm
    cfo = pit.latest("cfo", "FY", now)
    if cfo and mcap:
        capex = pit.at_period("capex", "FY", cfo[0], now)
        if capex is not None:
            out["fcf_yield"] = (cfo[1] - capex) / mcap * 100
    if mcap is not None and equity:
        out["pb"] = _ratio(mcap, equity[1])

    # Quality
    ebit = pit.latest("ebit", "FY", now)
    pat = pit.latest("pat", "FY", now)
    if ebit and equity:
        capital = equity[1] + (debt[1] if debt else 0.0)
        r = _ratio(ebit[1], capital)
        out["roce"] = r * 100 if r is not None else None
    if pat and equity:
        r = _ratio(pat[1], equity[1])
        out["roe"] = r * 100 if r is not None else None
    if debt and equity:
        out["debt_equity"] = _ratio(debt[1], equity[1])
    if ebit:
        interest = pit.at_period("interest", "FY", ebit[0], now)
        if interest is not None:
            out["interest_cover"] = 100.0 if interest <= 0 else min(ebit[1] / interest, 100.0)
    if cfo and pat and pat[0] == cfo[0]:
        out["cfo_pat"] = _ratio(cfo[1], pat[1])
    for key, fld in (
        ("gnpa", "gnpa_pct"),
        ("nnpa", "nnpa_pct"),
        ("casa", "casa_pct"),
        ("car", "car_pct"),
        ("credit_cost", "credit_cost_pct"),
    ):
        latest = pit.latest_any(fld, now)
        if latest:
            out[key] = latest[1]

    # Growth
    out["revenue_cagr_3y"] = _cagr(pit.series("revenue", "FY", now))
    out["eps_cagr_3y"] = _cagr(pit.series("eps", "FY", now))
    rev_now, rev_prev = ttm(pit, "revenue", now), ttm(pit, "revenue", now, offset=4)
    if rev_now is not None and rev_prev and rev_prev > 0:
        out["revenue_yoy_ttm"] = (rev_now / rev_prev - 1) * 100

    # Risk and ownership
    pledge = pit.latest("promoter_pledge_pct", "Q", now)
    if pledge:
        out["pledge_pct"] = pledge[1]
    prom = consecutive_quarters(pit.series("promoter_pct", "Q", now), 2)
    if prom:
        out["promoter_change_qoq"] = prom[1] - prom[0]
    fii = pit.series("fii_pct", "Q", now)
    dii = dict(pit.series("dii_pct", "Q", now))
    inst = [(d, v + dii[d]) for d, v in fii if d in dii]
    pair = consecutive_quarters(inst, 2)
    if pair:
        out["institutional_change_qoq"] = pair[1] - pair[0]

    clean = {k: v for k, v in out.items() if v is not None and math.isfinite(v)}
    return clean, int(mcap) if mcap is not None else None, quarters


def governance_values(conn: psycopg.Connection[TupleRow], as_of: date) -> dict[str, float]:
    """100 = checked and clean for 3 years; 0 = an event; absent = never checked."""
    end = cutoff(as_of)
    checked = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT isin FROM governance_checks WHERE checked_at < %s", (end,)
        )
    }
    flagged = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT isin FROM governance_events WHERE available_from < %s "
            "AND event_date > %s AND event_date <= %s",
            (end, as_of - timedelta(days=3 * 365), as_of),
        )
    }
    return {isin: 0.0 if isin in flagged else 100.0 for isin in checked | flagged}


# --- Screen run ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ScreenRun:
    id: int
    as_of: date
    definitions_sha: str
    stocks: int


def compute_screen(
    conn: psycopg.Connection[TupleRow], as_of: date, defs: Definitions | None = None
) -> tuple[list[StockInput], dict[str, dict[str, float]]]:
    defs = defs or load_definitions()
    fields = [f for group in defs.fields.values() for f in group]
    secs = conn.execute(
        "SELECT isin, name, nse_symbol, industry, sector, financial_type, status, surveillance "
        "FROM securities WHERE status <> 'DELISTED' ORDER BY isin"
    ).fetchall()
    prices = load_prices(conn, as_of)
    index = load_index(conn, as_of)
    month_ends = load_month_end_closes(conn, as_of)
    funds = load_fundamentals(conn, as_of, fields)
    governance = governance_values(conn, as_of)
    gate_start = as_of - timedelta(days=GATE_LOOKBACK_DAYS)

    stocks: list[StockInput] = []
    values: dict[str, dict[str, float]] = {}
    for isin, name, symbol, industry, sector, ftype, status, surveillance in secs:
        p = prices.get(isin)
        recent = [v for d, v in zip(p.dates, p.values, strict=True) if d > gate_start] if p else []
        traded = sorted(v for v in recent if v is not None)
        median_value = int(statistics.median(traded)) if traded else None
        close = float(p.closes[-1]) if p is not None and p.closes.size else None
        vals: dict[str, float] = price_factors(p, index) if p is not None else {}
        fvals, mcap, quarters = fundamental_factors(
            funds.get(isin, PitFundamentals()),
            as_of=as_of,
            close_paise=close,
            month_end_closes=month_ends.get(isin, []),
        )
        vals.update(fvals)
        if isin in governance:
            vals["governance_clean"] = governance[isin]
        stocks.append(
            StockInput(
                isin=isin,
                name=name,
                nse_symbol=symbol,
                industry=industry,
                sector=sector,
                financial_type=ftype,
                status=status,
                surveillance=surveillance,
                median_value_paise=median_value,
                price_observations=len(recent),
                mcap_paise=mcap,
                quarters=quarters,
            )
        )
        values[isin] = {k: float(v) for k, v in vals.items() if math.isfinite(v)}
    return stocks, values


def run_screen(
    conn: psycopg.Connection[TupleRow], as_of: date, defs: Definitions | None = None
) -> ScreenRun:
    defs = defs or load_definitions()
    stocks, values = compute_screen(conn, as_of, defs)
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO screen_runs (as_of, definitions_sha, stocks) VALUES (%s, %s, %s) "
            "RETURNING id",
            (as_of, defs.sha256, len(stocks)),
        ).fetchone()
        assert row is not None
        run_id = int(row[0])
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO screen_inputs (run_id, isin, name, nse_symbol, industry, sector,
                    financial_type, status, surveillance, median_value_paise, price_observations,
                    mcap_paise, quarters)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        run_id,
                        s.isin,
                        s.name,
                        s.nse_symbol,
                        s.industry,
                        s.sector,
                        s.financial_type,
                        s.status,
                        s.surveillance,
                        s.median_value_paise,
                        s.price_observations,
                        s.mcap_paise,
                        s.quarters,
                    )
                    for s in stocks
                ],
            )
            cur.executemany(
                "INSERT INTO factor_values (run_id, isin, factor, value) VALUES (%s, %s, %s, %s)",
                [(run_id, isin, k, v) for isin, vals in values.items() for k, v in vals.items()],
            )
    return ScreenRun(run_id, as_of, defs.sha256, len(stocks))


def latest_run(conn: psycopg.Connection[TupleRow], as_of: date | None = None) -> ScreenRun | None:
    row = conn.execute(
        "SELECT id, as_of, definitions_sha, stocks FROM screen_runs "
        "WHERE %(d)s::date IS NULL OR as_of <= %(d)s ORDER BY as_of DESC, id DESC LIMIT 1",
        {"d": as_of},
    ).fetchone()
    return ScreenRun(*row) if row else None


def load_run(
    conn: psycopg.Connection[TupleRow], run_id: int
) -> tuple[list[StockInput], dict[str, dict[str, float]]]:
    stocks = [
        StockInput(*r)
        for r in conn.execute(
            "SELECT isin, name, nse_symbol, industry, sector, financial_type, status, "
            "surveillance, median_value_paise, price_observations, mcap_paise, quarters "
            "FROM screen_inputs "
            "WHERE run_id = %s ORDER BY isin",
            (run_id,),
        )
    ]
    values: dict[str, dict[str, float]] = defaultdict(dict)
    for isin, factor, value in conn.execute(
        "SELECT isin, factor, value FROM factor_values WHERE run_id = %s", (run_id,)
    ):
        values[isin][factor] = value
    return stocks, dict(values)
