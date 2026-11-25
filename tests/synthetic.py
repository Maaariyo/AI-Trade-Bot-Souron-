"""A small synthetic market for factor tests: securities, prices, index, fundamentals.

Deterministic for a given seed. Results are published 40 days after each period
end, so point-in-time rules can be tested against known dates.
"""

from datetime import UTC, date, datetime, time, timedelta

import numpy as np
import psycopg
from psycopg.rows import TupleRow

AS_OF = date(2026, 11, 18)
INDUSTRIES = [
    ("Cement", "Materials", "NONE"),
    ("IT Services", "Technology", "NONE"),
    ("Auto Parts", "Consumer Discretionary", "NONE"),
    ("Private Sector Bank", "Financial Services", "BANK"),
]
CRORE = 10_000_000 * 100  # paise


def isin_for(i: int) -> str:
    return f"INE{i:05d}A01{i % 10}"


def trading_days(end: date, n: int) -> list[date]:
    days: list[date] = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def quarter_ends(end: date, n: int) -> list[date]:
    out: list[date] = []
    y, m = end.year, end.month
    while len(out) < n:
        qm = ((m - 1) // 3) * 3  # month index of the quarter start - 1
        if qm == 0:
            y, qm = y - 1, 12
        last_day = date(y + (qm == 12), qm % 12 + 1, 1) - timedelta(days=1)
        if last_day < end - timedelta(days=45) or out:
            out.append(last_day)
        y, m = last_day.year, last_day.month - 2 if last_day.month > 2 else last_day.month + 10
        if last_day.month <= 2:
            y -= 1
    return sorted(out)


def published(period_end: date) -> datetime:
    return datetime.combine(period_end + timedelta(days=40), time(10, 0), tzinfo=UTC)


def seed_market(
    conn: psycopg.Connection[TupleRow],
    *,
    per_industry: int = 12,
    seed: int = 1,
    as_of: date = AS_OF,
) -> list[str]:
    rng = np.random.default_rng(seed)
    days = trading_days(as_of, 1_300)  # about 5 years
    market = np.cumprod(1 + rng.normal(0.0004, 0.01, len(days))) * 20_000
    conn.execute(
        "INSERT INTO index_prices (index_code, trade_date, open, high, low, close, source) "
        "SELECT 'NIFTY 500', d, c, c, c, c, 'synthetic' FROM unnest(%s::date[], %s::numeric[]) "
        "AS t(d, c)",
        (days, [round(float(x), 4) for x in market]),
    )
    isins: list[str] = []
    q_ends = quarter_ends(as_of, 24)
    fy_ends = [d for d in q_ends if d.month == 3]
    i = 0
    for industry, sector, ftype in INDUSTRIES:
        for _ in range(per_industry):
            i += 1
            isin = isin_for(i)
            isins.append(isin)
            conn.execute(
                "INSERT INTO securities (isin, name, nse_symbol, status, first_seen, last_seen, "
                "industry, sector, financial_type) "
                "VALUES (%s, %s, %s, 'ACTIVE', %s, %s, %s, %s, %s)",
                (isin, f"Synthetic {i} Ltd", f"SYN{i}", as_of, as_of, industry, sector, ftype),
            )
            beta = rng.uniform(0.6, 1.4)
            mret = np.diff(market) / market[:-1]
            rets = 0.0003 + beta * mret + rng.normal(0, 0.012, len(mret))
            closes = np.concatenate(([rng.uniform(100, 3000)], np.ones(len(mret))))
            closes[1:] = closes[0] * np.cumprod(1 + rets)
            volume = int(rng.uniform(2e3, 2e6))  # some names fall below Rs 5 crore a day
            close_paise = [max(int(c * 100), 1) for c in closes]
            conn.execute(
                "INSERT INTO daily_prices (isin, exchange, trade_date, open_paise, high_paise, "
                "low_paise, close_paise, volume, traded_value_paise, source) "
                "SELECT %s, 'NSE', d, c, c, c, c, %s, c::bigint * %s, 'synthetic' "
                "FROM unnest(%s::date[], %s::bigint[]) AS t(d, c)",
                (isin, volume, volume, days, close_paise),
            )
            shares = int(rng.uniform(5e7, 5e8))
            growth = rng.uniform(-0.02, 0.06)
            base_rev = rng.uniform(200, 5000) * CRORE / 4
            rows: list[tuple[object, ...]] = []
            for k, qe in enumerate(q_ends):
                rev = base_rev * (1 + growth) ** k
                margin = rng.uniform(0.1, 0.3)
                pat = rev * margin * 0.5
                vals = {"revenue": rev, "pat": pat, "eps": pat / shares}
                if ftype == "NONE":
                    vals["ebitda"] = rev * margin
                for fld, v in vals.items():
                    rows.append((isin, qe, "Q", "PL", fld, v, "paise", published(qe)))
                holding = {
                    "promoter_pct": 50 + rng.normal(0, 2),
                    "promoter_pledge_pct": max(rng.normal(3, 3), 0),
                    "fii_pct": 15 + rng.normal(0, 2),
                    "dii_pct": 12 + rng.normal(0, 2),
                }
                for fld, v in holding.items():
                    rows.append((isin, qe, "Q", "SHAREHOLDING", fld, v, "percent", published(qe)))
                if ftype == "BANK":
                    ratios = {
                        "gnpa_pct": rng.uniform(1, 6),
                        "nnpa_pct": rng.uniform(0.2, 2),
                        "casa_pct": rng.uniform(25, 50),
                        "car_pct": rng.uniform(13, 20),
                        "credit_cost_pct": rng.uniform(0.3, 2),
                    }
                    for fld, v in ratios.items():
                        rows.append((isin, qe, "Q", "RATIO", fld, v, "percent", published(qe)))
            for fe in fy_ends:
                k = q_ends.index(fe)
                rev = sum(base_rev * (1 + growth) ** j for j in range(k - 3, k + 1))
                pat = rev * 0.1
                equity = rev * rng.uniform(0.4, 1.5)
                fy = {
                    "revenue": rev,
                    "pat": pat,
                    "eps": pat / shares,
                    "ebit": rev * 0.15,
                    "interest": rev * rng.uniform(0, 0.03),
                    "cfo": pat * rng.uniform(0.6, 1.4),
                    "capex": rev * rng.uniform(0.02, 0.1),
                    "equity": equity,
                    "total_debt": equity * rng.uniform(0, 1.2),
                    "cash": rev * rng.uniform(0.02, 0.2),
                }
                for fld, v in fy.items():
                    stmt = (
                        "BS"
                        if fld in ("equity", "total_debt", "cash")
                        else "CF"
                        if fld in ("cfo", "capex")
                        else "PL"
                    )
                    rows.append((isin, fe, "FY", stmt, fld, v, "paise", published(fe)))
                rows.append(
                    (isin, fe, "FY", "BS", "shares_outstanding", shares, "shares", published(fe))
                )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO fundamentals (isin, period_end, period_type, statement, field, "
                    "value, unit, available_from, source) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'synthetic')",
                    rows,
                )
            conn.execute(
                "INSERT INTO governance_checks (isin, checked_at, source) VALUES (%s, %s, 't')",
                (isin, datetime.combine(as_of - timedelta(days=30), time(0), tzinfo=UTC)),
            )
    conn.execute(
        "INSERT INTO governance_events (isin, event_type, event_date, available_from, source) "
        "VALUES (%s, 'AUDITOR_RESIGNATION', %s, %s, 't')",
        (isins[0], as_of - timedelta(days=200), published(as_of - timedelta(days=240))),
    )
    return isins
