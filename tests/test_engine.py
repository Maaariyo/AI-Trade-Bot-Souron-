import time
from dataclasses import replace

import numpy as np
import pytest

from services.factors.definitions import (
    Gates,
    classify_financial_type,
    load_definitions,
    load_presets,
)
from services.factors.engine import (
    CRORE_PAISE,
    StockInput,
    apply_weights,
    gate_reasons,
    percentile_ranks,
    rank_factors,
    score_universe,
)

DEFS = load_definitions()
PRESETS = load_presets()
GATES = Gates()


def stock(
    isin: str, industry: str | None = "Cement", sector: str | None = "Materials", **kw: object
) -> StockInput:
    base = StockInput(
        isin=isin,
        name=isin,
        nse_symbol=isin,
        industry=industry,
        sector=sector,
        financial_type="NONE",
        status="ACTIVE",
        surveillance="NONE",
        median_value_paise=50 * CRORE_PAISE,
        price_observations=60,
        mcap_paise=5_000 * CRORE_PAISE,
        quarters=12,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def only(weights: dict[str, float]) -> dict[str, float]:
    return {fam: weights.get(fam, 0.0) for fam in DEFS.families}


# --- Percentiles ------------------------------------------------------------------------


def test_percentiles_are_0_to_100_with_average_ties() -> None:
    assert percentile_ranks(np.array([5.0, 1, 3, 2, 4])).tolist() == [100, 0, 50, 25, 75]
    assert percentile_ranks(np.array([1.0, 1, 3])).tolist() == [25, 25, 100]
    assert percentile_ranks(np.array([7.0])).tolist() == [50]


def test_winsorising_ties_an_outlier_with_the_99th_percentile() -> None:
    vals = np.array([*range(1, 101), 1e9], dtype=float)
    pct = percentile_ranks(vals)
    assert pct[-1] == pct[-2]  # 1e9 is clipped to the 99th percentile value


# --- Gates ---------------------------------------------------------------------------


def test_gates_run_price_step_before_fundamental_step() -> None:
    illiquid = stock("A", median_value_paise=CRORE_PAISE, mcap_paise=None, quarters=2)
    assert gate_reasons(illiquid, GATES) == ["median traded value below Rs 5 crore"]
    small = stock("B", mcap_paise=100 * CRORE_PAISE, quarters=4)
    assert gate_reasons(small, GATES) == [
        "market cap below Rs 500 crore",
        "only 4 quarters of financials",
    ]
    asm = stock("C", surveillance="ASM")
    assert gate_reasons(asm, GATES) == []
    assert gate_reasons(asm, replace(GATES, exclude_asm=True)) == ["under ASM"]
    assert gate_reasons(stock("D", surveillance="GSM"), GATES) == ["under GSM"]


# --- Ranking groups, directions and composite ------------------------------------------


def test_direction_flip_and_composite() -> None:
    stocks = [stock(f"S{i}") for i in range(11)]
    values = {s.isin: {"roe": float(i), "debt_equity": float(i)} for i, s in enumerate(stocks)}
    res = score_universe(stocks, values, DEFS, only({"quality": 10}), GATES, coverage_min=0.0)
    top = {s.isin: s for s in res.stocks}
    assert top["S10"].percentiles == {"roe": 100.0, "debt_equity": 0.0}  # debt: lower is better
    # The other quality factors have no data anywhere, so they leave the weights.
    assert top["S10"].composite == pytest.approx(50.0)
    assert top["S10"].coverage == pytest.approx(1.0)


def test_small_industry_falls_back_to_sector_then_universe() -> None:
    stocks = [stock(f"A{i}", industry="Cement") for i in range(10)]
    stocks += [stock(f"B{i}", industry="Glass", sector="Materials") for i in range(3)]
    stocks += [stock(f"C{i}", industry="Toys", sector="Leisure") for i in range(2)]
    values = {s.isin: {"roe": float(i)} for i, s in enumerate(stocks)}
    res = {
        s.isin: s for s in score_universe(stocks, values, DEFS, only({"quality": 5}), GATES).stocks
    }
    assert res["A0"].levels["roe"] == "industry"  # 10 cement stocks
    assert res["B0"].levels["roe"] == "sector"  # 13 materials stocks
    assert res["C0"].levels["roe"] == "universe"  # 2 leisure stocks
    assert res["A9"].percentiles["roe"] == 100.0  # best cement stock within cement


def test_coverage_rule_marks_thin_data_unranked() -> None:
    stocks = [stock(f"S{i}") for i in range(12)]
    full = {"roe": 1.0, "roce": 1.0, "debt_equity": 1.0, "interest_cover": 1.0, "cfo_pat": 1.0}
    values = {s.isin: {k: v * i for k, v in full.items()} for i, s in enumerate(stocks)}
    for k in ("roce", "debt_equity"):  # S0 keeps 3 of 5 quality factors: 60% < 70%
        del values["S0"][k]
    del values["S1"]["roce"]  # S1 keeps 4 of 5: 80%
    res = {
        s.isin: s for s in score_universe(stocks, values, DEFS, only({"quality": 7}), GATES).stocks
    }
    assert (
        res["S0"].coverage == pytest.approx(0.6) and res["S0"].thin_data and res["S0"].rank is None
    )
    assert res["S1"].coverage == pytest.approx(0.8) and not res["S1"].thin_data
    assert res["S1"].rank is not None


def test_factor_with_no_data_anywhere_is_unavailable_not_missing() -> None:
    stocks = [stock(f"S{i}") for i in range(12)]
    values = {s.isin: {"roe": float(i)} for i, s in enumerate(stocks)}
    res = score_universe(stocks, values, DEFS, only({"quality": 7, "governance": 10}), GATES)
    assert "governance_clean" in res.unavailable_factors
    assert all(s.coverage == pytest.approx(1.0) for s in res.stocks)  # roe is all quality has
    assert [s.rank for s in res.ranked][:3] == [1, 2, 3]


def test_governance_is_absolute_not_ranked() -> None:
    stocks = [stock(f"S{i}") for i in range(12)]
    values = {s.isin: {"governance_clean": 100.0 if i else 0.0} for i, s in enumerate(stocks)}
    res = {
        s.isin: s
        for s in score_universe(stocks, values, DEFS, only({"governance": 10}), GATES).stocks
    }
    assert res["S0"].percentiles["governance_clean"] == 0.0
    assert res["S5"].percentiles["governance_clean"] == 100.0


def test_bank_uses_its_own_factor_set() -> None:
    stocks = [
        stock(f"B{i}", industry="Banks", sector="Financials", financial_type="BANK")
        for i in range(10)
    ]
    stocks += [stock(f"N{i}") for i in range(10)]
    values = {
        **{
            s.isin: {"pb": float(i), "casa": float(i), "ev_ebitda": 9.0}
            for i, s in enumerate(stocks[:10])
        },
        **{s.isin: {"ev_ebitda": float(i), "pb": 9.0} for i, s in enumerate(stocks[10:])},
    }
    res = {
        s.isin: s
        for s in score_universe(
            stocks, values, DEFS, only({"value": 6, "quality": 7}), GATES, coverage_min=0
        ).stocks
    }
    assert set(res["B3"].percentiles) == {"pb", "casa"}  # ev_ebitda ignored for banks
    assert set(res["N3"].percentiles) == {"ev_ebitda"}  # pb ignored for non-financials


def test_classify_financial_type() -> None:
    assert classify_financial_type("Private Sector Bank", "Financial Services") == "BANK"
    assert classify_financial_type("Housing Finance Company", None) == "NBFC"
    assert classify_financial_type("Cement", "Materials") == "NONE"


def test_presets_match_spec_table() -> None:
    assert PRESETS.presets["Balanced"] == {
        "value": 6,
        "quality": 7,
        "growth": 6,
        "momentum": 5,
        "risk": 5,
        "ownership": 4,
        "governance": 8,
    }
    assert PRESETS.presets["Slightly Safe"]["governance"] == 10
    assert PRESETS.presets["Slightly Risky"]["momentum"] == 9


# --- Speed: the Phase 2 done-when bar is a re-rank in under 1 second --------------------


def test_full_universe_reranks_in_under_a_second() -> None:
    rng = np.random.default_rng(7)
    industries = [f"Ind{i}" for i in range(150)]
    stocks = [
        stock(
            f"S{i:05d}",
            industry=industries[i % 150],
            sector=f"Sec{i % 20}",
            financial_type="BANK" if i % 40 == 0 else "NONE",
        )
        for i in range(5_500)
    ]
    keys = [f.key for f in DEFS.factors]
    values = {
        s.isin: {
            k: float(v)
            for k, v in zip(keys, rng.normal(size=len(keys)), strict=True)
            if rng.random() > 0.1
        }
        for s in stocks
    }
    start = time.perf_counter()
    ranked = rank_factors(stocks, values, DEFS, GATES)
    rank_time = time.perf_counter() - start
    start = time.perf_counter()
    res = apply_weights(ranked, DEFS, PRESETS.presets["Slightly Risky"])
    weight_time = time.perf_counter() - start
    assert len(res.ranked) > 5_000
    assert rank_time < 1.0, f"gate change re-rank took {rank_time:.2f}s"
    assert weight_time < 0.25, f"slider re-rank took {weight_time:.2f}s"
    # Re-weighting a cached ranking leaves the cache untouched.
    again = apply_weights(ranked, DEFS, PRESETS.presets["Balanced"])
    assert again.ranked[0].isin != "" and ranked.results[0].composite is None
