from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

import numpy as np
import psycopg
import pytest
from psycopg.rows import TupleRow

from services.factors.compute import (
    PitFundamentals,
    PriceSeries,
    cutoff,
    fundamental_factors,
    latest_run,
    load_run,
    price_factors,
    run_screen,
    ttm,
)
from services.factors.definitions import Gates, load_definitions, load_presets
from services.factors.engine import score_universe
from tests.synthetic import AS_OF, quarter_ends, seed_market, trading_days

Conn = psycopg.Connection[TupleRow]
DEFS = load_definitions()


def _at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, tzinfo=UTC)


def test_quarter_generator_is_consecutive() -> None:
    q = quarter_ends(AS_OF, 24)
    assert len(q) == 24 and q[-1] == date(2026, 9, 30)
    assert all(80 <= (b - a).days <= 100 for a, b in pairwise(q))


# --- Point in time ---------------------------------------------------------------------


def _eps_pit(extra_avail: datetime) -> PitFundamentals:
    pit = PitFundamentals()
    for qe in quarter_ends(date(2026, 8, 31), 8):  # through 2026-06-30
        pit.add("eps", "Q", qe, _at(qe + timedelta(days=40)), 1000.0)  # Rs 10 a quarter
    # A newer quarter that is not public yet on AS_OF.
    pit.add("eps", "Q", date(2026, 9, 30), extra_avail, 100_000.0)
    return pit


def test_unpublished_quarter_is_invisible() -> None:
    hidden = _eps_pit(_at(AS_OF + timedelta(days=1)))
    assert ttm(hidden, "eps", cutoff(AS_OF)) == 4000.0
    visible = _eps_pit(_at(AS_OF - timedelta(days=1)))
    assert ttm(visible, "eps", cutoff(AS_OF)) == 3000.0 + 100_000.0


def test_restatement_applies_only_from_its_available_date() -> None:
    pit = PitFundamentals()
    pe = date(2026, 6, 30)
    pit.add("roe_input", "FY", pe, _at(date(2026, 8, 1)), 10.0)
    pit.add("roe_input", "FY", pe, _at(date(2026, 12, 1)), 12.0)  # restated later
    assert pit.latest("roe_input", "FY", cutoff(AS_OF)) == (pe, 10.0)
    assert pit.latest("roe_input", "FY", cutoff(date(2026, 12, 2))) == (pe, 12.0)


def test_pe_vs_own_median_uses_month_end_history() -> None:
    pit = PitFundamentals()
    for qe in quarter_ends(AS_OF, 24):
        pit.add("eps", "Q", qe, _at(qe + timedelta(days=40)), 1000.0)  # TTM EPS Rs 40
    month_ends = [(date(2024, m, 28), 40_000.0) for m in range(1, 13)]
    month_ends += [(date(2025, m, 28), 40_000.0) for m in range(1, 13)]  # P/E 10 history
    out, _, _ = fundamental_factors(
        pit, as_of=AS_OF, close_paise=80_000.0, month_end_closes=month_ends
    )
    assert out["pe_vs_median"] == pytest.approx(2.0)  # P/E 20 today vs median 10


def test_price_factors_on_a_known_series() -> None:
    days = trading_days(AS_OF, 300)
    closes = (100.0 * 1.001 ** np.arange(300)).astype(np.float64)
    index = {d: 1000.0 * (1 + 0.01 * np.sin(k)) for k, d in enumerate(days)}
    out = price_factors(PriceSeries(days, closes, [None] * 300), index)
    assert out["mom_12_1"] == pytest.approx((1.001**231 - 1) * 100)
    assert out["vol_1y"] == pytest.approx(0.0, abs=1e-9)  # constant daily return
    assert out["max_drawdown_1y"] == pytest.approx(0.0)
    assert out["price_vs_200dma"] > 0
    assert "beta_1y" in out and "rel_strength_12m" in out


# --- Full screen run on a synthetic market -----------------------------------------------


@pytest.mark.integration
def test_screen_run_round_trip_and_scoring(db: Conn) -> None:
    isins = seed_market(db, per_industry=12)
    run = run_screen(db, AS_OF)
    assert run.stocks == len(isins) == 48
    stocks, values = load_run(db, run.id)
    assert latest_run(db) == run

    normal, bank = values[isins[1]], values[isins[-1]]
    for key in (
        "pe_vs_median",
        "ev_ebitda",
        "roe",
        "revenue_cagr_3y",
        "mom_12_1",
        "vol_1y",
        "beta_1y",
        "pledge_pct",
        "promoter_change_qoq",
        "governance_clean",
    ):
        assert key in normal, key
    assert {"pb", "gnpa", "casa", "car"} <= bank.keys() and "ev_ebitda" not in bank
    assert values[isins[0]]["governance_clean"] == 0.0  # the auditor resignation
    assert normal["governance_clean"] == 100.0

    by_isin = {s.isin: s for s in stocks}
    assert by_isin[isins[1]].quarters == 24
    assert by_isin[isins[1]].mcap_paise is not None

    presets = load_presets()
    res = score_universe(stocks, values, DEFS, presets.presets["Balanced"], Gates())
    assert res.unavailable_factors == []
    ranked = res.ranked
    assert ranked and all(r.coverage and r.coverage >= 0.7 for r in ranked)
    failed = [s for s in res.stocks if not s.passed]
    assert all(s.reasons for s in failed)
