"""Stage 1 scoring engine (SPEC section 5): pure functions, no I/O.

Inputs are one screen run's raw factor values. Everything a slider or gate
change affects is recomputed here, so a re-rank needs no database work:

1. Hard gates, price step then fundamental step.
2. For each factor, rank within the stock's industry among stocks that pass
   the gates and have a value; if fewer than `min_group_size` have one, within
   its sector; if still too few, within the whole passing universe.
3. Winsorise at the 1st and 99th percentiles, convert to a 0-100 percentile
   (ties share their average rank), and flip lower-is-better factors.
   `absolute` factors (governance) keep their 0-100 value.
4. S_i = sum(w_k p_ik) / sum(w_k) over factors with data, where w_k is the
   family weight split equally across the family's factors for that stock's
   type (ordinary, bank, NBFC). Coverage = available weight / applicable weight;
   below `coverage_min` the stock is "thin data" and is not ranked.

A factor with no value for any passing stock is "unavailable" (no data loaded
yet) and leaves every stock's weights, so missing feeds don't fail everyone's
coverage. The result lists unavailable factors so the UI can say so.
"""

from collections import defaultdict
from dataclasses import dataclass, field, replace

import numpy as np
import numpy.typing as npt

from services.factors.definitions import Definitions, FactorDef, Gates

CRORE_PAISE = 10_000_000 * 100


@dataclass(frozen=True)
class StockInput:
    isin: str
    name: str
    nse_symbol: str | None
    industry: str | None
    sector: str | None
    financial_type: str
    status: str
    surveillance: str
    median_value_paise: int | None
    price_observations: int
    mcap_paise: int | None
    quarters: int


@dataclass
class ScoredStock:
    isin: str
    name: str
    nse_symbol: str | None
    industry: str | None
    sector: str | None
    passed: bool
    reasons: list[str]
    composite: float | None = None
    coverage: float | None = None
    thin_data: bool = False
    rank: int | None = None
    percentiles: dict[str, float] = field(default_factory=dict)
    family_scores: dict[str, float] = field(default_factory=dict)
    levels: dict[str, str] = field(default_factory=dict)


@dataclass
class ScoreResult:
    stocks: list[ScoredStock]
    unavailable_factors: list[str]

    @property
    def ranked(self) -> list[ScoredStock]:
        return sorted((s for s in self.stocks if s.rank is not None), key=lambda s: s.rank or 0)


def gate_reasons(s: StockInput, gates: Gates) -> list[str]:
    """Why a stock fails. Fundamental gates are checked only after price gates pass."""
    reasons: list[str] = []
    if s.status != "ACTIVE":
        reasons.append(f"status {s.status}")
    if s.surveillance == "GSM" and gates.exclude_gsm:
        reasons.append("under GSM")
    if s.surveillance == "ASM" and gates.exclude_asm:
        reasons.append("under ASM")
    if s.price_observations < gates.min_price_observations:
        reasons.append(f"only {s.price_observations} trading days of prices")
    elif (s.median_value_paise or 0) < gates.min_median_value_crore * CRORE_PAISE:
        reasons.append(f"median traded value below Rs {gates.min_median_value_crore:g} crore")
    if reasons:
        return reasons
    if s.mcap_paise is None:
        reasons.append("no market cap (shares outstanding missing)")
    elif s.mcap_paise < gates.min_mcap_crore * CRORE_PAISE:
        reasons.append(f"market cap below Rs {gates.min_mcap_crore:g} crore")
    if s.quarters < gates.min_quarters:
        reasons.append(f"only {s.quarters} quarters of financials")
    return reasons


def percentile_ranks(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Winsorise at the 1st/99th percentiles, then 0-100 percentiles with average ties."""
    n = values.size
    if n == 1:
        return np.array([50.0])
    lo, hi = np.percentile(values, [1, 99])
    clipped = np.clip(values, lo, hi)
    _, inverse, counts = np.unique(clipped, return_inverse=True, return_counts=True)
    first_rank = np.concatenate(([0], np.cumsum(counts)[:-1]))  # 0-based rank of each value
    avg_rank = first_rank + (counts - 1) / 2.0
    return np.asarray(avg_rank[inverse] / (n - 1) * 100.0, dtype=np.float64)


def _factor_weights(
    defs: Definitions, family_weights: dict[str, float], available: set[str]
) -> dict[str, dict[str, float]]:
    """Per financial type: factor -> weight, splitting each family weight equally."""
    out: dict[str, dict[str, float]] = {}
    for ftype in ("NONE", "BANK", "NBFC"):
        applicable = [f for f in defs.factors if f.key in available and f.applies(ftype)]
        per_family: dict[str, list[FactorDef]] = defaultdict(list)
        for f in applicable:
            per_family[f.family].append(f)
        out[ftype] = {
            f.key: max(family_weights.get(fam, 0.0), 0.0) / len(members)
            for fam, members in per_family.items()
            for f in members
        }
    return out


@dataclass
class Ranked:
    """Gate results and percentiles. Depends on gates, not on weights, so it can be cached."""

    stocks: list[StockInput]
    results: list[ScoredStock]
    passing: list[int]
    available: set[str]
    unavailable: list[str]


def rank_factors(
    stocks: list[StockInput],
    values: dict[str, dict[str, float]],
    defs: Definitions,
    gates: Gates,
    *,
    min_group_size: int = 10,
) -> Ranked:
    results = [
        ScoredStock(
            isin=s.isin,
            name=s.name,
            nse_symbol=s.nse_symbol,
            industry=s.industry,
            sector=s.sector,
            passed=False,
            reasons=gate_reasons(s, gates),
        )
        for s in stocks
    ]
    passing = [(i, s) for i, s in enumerate(stocks) if not results[i].reasons]
    for i, _ in passing:
        results[i].passed = True

    available = {
        f.key
        for f in defs.factors
        if any(f.key in values.get(s.isin, {}) and f.applies(s.financial_type) for _, s in passing)
    }
    unavailable = [f.key for f in defs.factors if f.key not in available]

    for f in defs.factors:
        if f.key not in available:
            continue
        members = [
            (i, s, values[s.isin][f.key])
            for i, s in passing
            if f.applies(s.financial_type) and f.key in values.get(s.isin, {})
        ]
        if f.normalise == "absolute":
            for i, _, v in members:
                results[i].percentiles[f.key] = float(np.clip(v, 0.0, 100.0))
                results[i].levels[f.key] = "absolute"
            continue
        by_industry: dict[str | None, list[int]] = defaultdict(list)
        by_sector: dict[str | None, list[int]] = defaultdict(list)
        for pos, (_, s, _) in enumerate(members):
            by_industry[s.industry].append(pos)
            by_sector[s.sector].append(pos)
        groups: dict[tuple[str, str | None], list[int]] = defaultdict(list)
        for pos, (_, s, _) in enumerate(members):
            if s.industry is not None and len(by_industry[s.industry]) >= min_group_size:
                groups[("industry", s.industry)].append(pos)
            elif s.sector is not None and len(by_sector[s.sector]) >= min_group_size:
                groups[("sector", s.sector)].append(pos)
            else:
                groups[("universe", None)].append(pos)
        for (level, _), positions in groups.items():
            vals = np.array([members[p][2] for p in positions], dtype=np.float64)
            pct = percentile_ranks(vals)
            if f.direction == "lower":
                pct = 100.0 - pct
            for p, score in zip(positions, pct, strict=True):
                idx = members[p][0]
                results[idx].percentiles[f.key] = float(score)
                results[idx].levels[f.key] = level

    return Ranked(stocks, results, [i for i, _ in passing], available, unavailable)


def apply_weights(
    ranked: Ranked,
    defs: Definitions,
    family_weights: dict[str, float],
    *,
    coverage_min: float = 0.70,
) -> ScoreResult:
    """Composite scores, coverage and ranks. Never mutates `ranked`."""
    results = [replace(r, family_scores={}) for r in ranked.results]
    available = ranked.available
    weights = _factor_weights(defs, family_weights, available)
    family_of = {f.key: f.family for f in defs.factors}
    for i in ranked.passing:
        r = results[i]
        w = weights.get(ranked.stocks[i].financial_type, weights["NONE"])
        total = sum(w.values())
        have = {k: pv for k, pv in r.percentiles.items() if k in w}
        got = sum(w[k] for k in have)
        if total <= 0:
            r.coverage, r.thin_data = None, True
            continue
        r.coverage = got / total
        r.thin_data = r.coverage < coverage_min
        if got > 0:
            r.composite = sum(w[k] * pv for k, pv in have.items()) / got
        fam_num: dict[str, float] = defaultdict(float)
        fam_den: dict[str, float] = defaultdict(float)
        for k, pv in have.items():
            fam_num[family_of[k]] += pv
            fam_den[family_of[k]] += 1
        r.family_scores = {fam: fam_num[fam] / fam_den[fam] for fam in fam_num}

    rankable = sorted(
        (r for r in results if r.passed and not r.thin_data and r.composite is not None),
        key=lambda r: (-(r.composite or 0.0), r.isin),
    )
    for n, r in enumerate(rankable, start=1):
        r.rank = n
    return ScoreResult(results, ranked.unavailable)


def score_universe(
    stocks: list[StockInput],
    values: dict[str, dict[str, float]],
    defs: Definitions,
    family_weights: dict[str, float],
    gates: Gates,
    *,
    coverage_min: float = 0.70,
    min_group_size: int = 10,
) -> ScoreResult:
    ranked = rank_factors(stocks, values, defs, gates, min_group_size=min_group_size)
    return apply_weights(ranked, defs, family_weights, coverage_min=coverage_min)
