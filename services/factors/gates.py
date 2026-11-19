"""Hard gates, step 1: price gates (SPEC section 5).

Price gates run before any fundamentals call, so the vendor is only asked
about stocks that can pass. Fundamental gates (market cap, 8 quarters) arrive
in Phase 2. Status and surveillance are the security master's current values;
point-in-time gates for backtests come from security_status_history in Phase 7.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import psycopg
from psycopg.rows import TupleRow

CRORE_PAISE = 10_000_000 * 100


@dataclass(frozen=True)
class PriceGateConfig:
    min_median_value_paise: int = 5 * CRORE_PAISE  # Rs 5 crore a day
    lookback_days: int = 91  # about 3 months
    min_observations: int = 20
    exclude_gsm: bool = True
    exclude_asm: bool = False


@dataclass(frozen=True)
class GateResult:
    isin: str
    passed: bool
    median_value_paise: int | None
    observations: int
    reasons: list[str] = field(default_factory=list)


def price_gate_results(
    conn: psycopg.Connection[TupleRow], *, as_of: date, cfg: PriceGateConfig | None = None
) -> list[GateResult]:
    """One result per non-delisted security, with the reasons it failed."""
    cfg = cfg or PriceGateConfig()
    start = as_of - timedelta(days=cfg.lookback_days)
    rows = conn.execute(
        """
        SELECT s.isin, s.status, s.surveillance,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY dp.traded_value_paise),
               count(dp.trade_date)
        FROM securities s
        LEFT JOIN daily_prices dp
          ON dp.isin = s.isin AND dp.trade_date > %s AND dp.trade_date <= %s
        WHERE s.status <> 'DELISTED'
        GROUP BY s.isin, s.status, s.surveillance
        ORDER BY s.isin
        """,
        (start, as_of),
    ).fetchall()
    out: list[GateResult] = []
    for isin, status, surveillance, median, obs in rows:
        reasons: list[str] = []
        if status != "ACTIVE":
            reasons.append(f"status {status}")
        if surveillance == "GSM" and cfg.exclude_gsm:
            reasons.append("under GSM")
        if surveillance == "ASM" and cfg.exclude_asm:
            reasons.append("under ASM")
        median_paise = int(median) if median is not None else None
        if obs < cfg.min_observations:
            reasons.append(f"only {obs} trading days of prices")
        elif median_paise is None or median_paise < cfg.min_median_value_paise:
            reasons.append("median traded value below Rs 5 crore")
        out.append(GateResult(isin, not reasons, median_paise, obs, reasons))
    return out
