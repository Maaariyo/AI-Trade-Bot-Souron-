"""Factor scores for the Screener and Weights Studio (SPEC section 8; Phase 2).

A screen run's inputs and its gate-dependent ranking are cached in memory, so a
weight change only re-applies weights (tens of milliseconds) and a gate change
only re-ranks (a few hundred). Nothing here calls an LLM.
"""

import time
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from services.db import connect
from services.factors.compute import ScreenRun, latest_run, load_run, run_screen
from services.factors.definitions import Gates, load_definitions, load_presets
from services.factors.engine import Ranked, ScoreResult, StockInput, apply_weights, rank_factors
from services.money import ist_date

router = APIRouter()


# --- Cached run data -------------------------------------------------------------------


@lru_cache(maxsize=4)
def _run_data(run_id: int) -> tuple[list[StockInput], dict[str, dict[str, float]]]:
    with connect() as conn:
        return load_run(conn, run_id)


@lru_cache(maxsize=16)
def _ranked(run_id: int, gates: Gates, min_group_size: int) -> Ranked:
    stocks, values = _run_data(run_id)
    return rank_factors(stocks, values, load_definitions(), gates, min_group_size=min_group_size)


def _latest() -> ScreenRun:
    with connect() as conn:
        run = latest_run(conn)
    if run is None:
        raise HTTPException(
            status_code=404, detail="No screen run yet. Run `make screen` after loading data."
        )
    return run


def _score(run: ScreenRun, weights: dict[str, float], gates: Gates) -> ScoreResult:
    presets = load_presets()
    ranked = _ranked(run.id, gates, presets.min_group_size)
    return apply_weights(ranked, load_definitions(), weights, coverage_min=presets.coverage_min)


# --- Models -------------------------------------------------------------------------


class GatesIn(BaseModel):
    min_median_value_crore: float = Field(ge=0, le=10_000)
    min_mcap_crore: float = Field(ge=0, le=10_000_000)
    min_quarters: int = Field(ge=0, le=40)
    exclude_gsm: bool
    exclude_asm: bool

    def to_gates(self) -> Gates:
        return Gates(**self.model_dump())


def _check_weights(weights: dict[str, float], low: float, high: float, keys: set[str]) -> None:
    if set(weights) != keys:
        raise ValueError(f"weights must cover exactly: {sorted(keys)}")
    if any(not low <= v <= high for v in weights.values()):
        raise ValueError(f"weights must be between {low:g} and {high:g}")


class PreviewIn(BaseModel):
    family_weights: dict[str, float]
    gates: GatesIn | None = None
    baseline_weights: dict[str, float] | None = None
    top: int = Field(default=20, ge=1, le=200)

    @field_validator("family_weights", "baseline_weights")
    @classmethod
    def _weights(cls, v: dict[str, float] | None) -> dict[str, float] | None:
        if v is not None:
            _check_weights(v, 0, 10, set(load_definitions().families))
        return v


class ProfileIn(BaseModel):
    family_weights: dict[str, float]
    gates: GatesIn
    agent_weights: dict[str, float]

    @field_validator("family_weights")
    @classmethod
    def _families(cls, v: dict[str, float]) -> dict[str, float]:
        _check_weights(v, 0, 10, set(load_definitions().families))
        return v

    @field_validator("agent_weights")
    @classmethod
    def _agents(cls, v: dict[str, float]) -> dict[str, float]:
        _check_weights(v, 0, 3, set(load_presets().agent_weights))
        return v


class ScoreRow(BaseModel):
    isin: str
    name: str
    nse_symbol: str | None
    industry: str | None
    sector: str | None
    passed: bool
    reasons: list[str]
    composite: float | None
    coverage: float | None
    thin_data: bool
    rank: int | None
    family_scores: dict[str, float]
    percentiles: dict[str, float] | None = None


class ScoresOut(BaseModel):
    run_id: int
    as_of: date
    weights: dict[str, float]
    unavailable_factors: list[str]
    rows: list[ScoreRow]


class PreviewRow(BaseModel):
    rank: int
    isin: str
    nse_symbol: str | None
    name: str
    composite: float
    move: int | None


class PreviewOut(BaseModel):
    run_id: int
    as_of: date
    passed: int
    ranked: int
    thin_data: int
    unavailable_factors: list[str]
    elapsed_ms: float
    top: list[PreviewRow]


def _row(s: Any, detail: bool) -> ScoreRow:
    return ScoreRow(
        isin=s.isin,
        name=s.name,
        nse_symbol=s.nse_symbol,
        industry=s.industry,
        sector=s.sector,
        passed=s.passed,
        reasons=s.reasons,
        composite=None if s.composite is None else round(s.composite, 2),
        coverage=None if s.coverage is None else round(s.coverage, 3),
        thin_data=s.thin_data,
        rank=s.rank,
        family_scores={k: round(v, 1) for k, v in s.family_scores.items()},
        percentiles={k: round(v, 1) for k, v in s.percentiles.items()} if detail else None,
    )


# --- Routes ---------------------------------------------------------------------------


@router.get("/presets")
def presets() -> dict[str, Any]:
    p, d = load_presets(), load_definitions()
    return {
        "families": list(d.families),
        "presets": p.presets,
        "default": p.default,
        "gates": GatesIn(
            **{k: v for k, v in p.gates.__dict__.items() if k in GatesIn.model_fields}
        ),
        "agent_weights": p.agent_weights,
        "coverage_min": p.coverage_min,
        "factors": [f.__dict__ for f in d.factors],
    }


@router.get("/scores")
def scores(
    preset: str | None = None,
    profile: str | None = None,
    detail: Annotated[bool, Query()] = False,
) -> ScoresOut:
    p = load_presets()
    weights, gates = p.presets[p.default], p.gates
    if profile:
        with connect() as conn:
            row = conn.execute(
                "SELECT family_weights, gates FROM weight_profiles WHERE name = %s", (profile,)
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no profile {profile}")
        weights, gates = row[0], GatesIn(**row[1]).to_gates()
    elif preset:
        if preset not in p.presets:
            raise HTTPException(status_code=404, detail=f"no preset {preset}")
        weights = p.presets[preset]
    run = _latest()
    res = _score(run, weights, gates)
    rows = sorted(res.stocks, key=lambda s: (s.rank is None, s.rank or 0, s.isin))
    return ScoresOut(
        run_id=run.id,
        as_of=run.as_of,
        weights=weights,
        unavailable_factors=res.unavailable_factors,
        rows=[_row(s, detail) for s in rows],
    )


@router.post("/scores/preview")
def preview(body: PreviewIn) -> PreviewOut:
    start = time.perf_counter()
    run = _latest()
    gates = body.gates.to_gates() if body.gates else load_presets().gates
    res = _score(run, body.family_weights, gates)
    before: dict[str, int] = {}
    if body.baseline_weights is not None:
        base = _score(run, body.baseline_weights, gates)
        before = {s.isin: s.rank for s in base.ranked if s.rank is not None}
    top = [
        PreviewRow(
            rank=s.rank or 0,
            isin=s.isin,
            nse_symbol=s.nse_symbol,
            name=s.name,
            composite=round(s.composite or 0.0, 2),
            move=(before[s.isin] - (s.rank or 0)) if s.isin in before else None,
        )
        for s in res.ranked[: body.top]
    ]
    return PreviewOut(
        run_id=run.id,
        as_of=run.as_of,
        passed=sum(s.passed for s in res.stocks),
        ranked=len(res.ranked),
        thin_data=sum(s.passed and s.thin_data for s in res.stocks),
        unavailable_factors=res.unavailable_factors,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 1),
        top=top,
    )


@router.get("/profiles")
def profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, family_weights, gates, agent_weights, updated_at FROM weight_profiles "
            "ORDER BY name"
        ).fetchall()
    return [
        {
            "name": r[0],
            "family_weights": r[1],
            "gates": r[2],
            "agent_weights": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


@router.put("/profiles/{name}", status_code=204)
def save_profile(name: str, body: ProfileIn) -> None:
    if not 1 <= len(name) <= 60:
        raise HTTPException(status_code=422, detail="profile name must be 1-60 characters")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO weight_profiles (name, family_weights, gates, agent_weights)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET family_weights = EXCLUDED.family_weights,
                gates = EXCLUDED.gates, agent_weights = EXCLUDED.agent_weights, updated_at = now()
            """,
            (
                name,
                Jsonb(body.family_weights),
                Jsonb(body.gates.model_dump()),
                Jsonb(body.agent_weights),
            ),
        )


def _run_screen_now() -> None:
    with connect() as conn:
        conn.autocommit = True
        run_screen(conn, ist_date(datetime.now(UTC)))


@router.post("/screen/run", status_code=202)
def screen_run(tasks: BackgroundTasks) -> dict[str, str]:
    tasks.add_task(_run_screen_now)
    return {"status": "started", "note": "a new screen run appears in /scores when it finishes"}
