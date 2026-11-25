from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import TupleRow

import services.api.scores as scores_api
from services.api.main import app
from services.db import connect
from services.factors.compute import run_screen
from services.factors.definitions import load_presets
from tests.synthetic import AS_OF, seed_market

Conn = psycopg.Connection[TupleRow]
PRESETS = load_presets()
GATES = {
    "min_median_value_crore": 5,
    "min_mcap_crore": 500,
    "min_quarters": 8,
    "exclude_gsm": True,
    "exclude_asm": False,
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, schema_url: str, db: Conn) -> Iterator[TestClient]:
    monkeypatch.setattr(scores_api, "connect", lambda **kw: connect(schema_url, **kw))
    scores_api._run_data.cache_clear()
    scores_api._ranked.cache_clear()
    yield TestClient(app)
    scores_api._run_data.cache_clear()
    scores_api._ranked.cache_clear()


@pytest.mark.integration
def test_no_run_yet_is_a_clear_404(client: TestClient) -> None:
    r = client.get("/scores")
    assert r.status_code == 404 and "make screen" in r.json()["detail"]


@pytest.mark.integration
def test_scores_preview_and_profiles(client: TestClient, db: Conn) -> None:
    seed_market(db, per_industry=12)
    run_screen(db, AS_OF)

    body: dict[str, Any] = client.get("/scores").json()
    assert body["weights"] == PRESETS.presets["Balanced"]
    rows = body["rows"]
    ranked = [r for r in rows if r["rank"] is not None]
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    assert all(r["reasons"] for r in rows if not r["passed"])
    assert rows[0]["percentiles"] is None  # detail only on request

    risky = PRESETS.presets["Slightly Risky"]
    p = client.post(
        "/scores/preview",
        json={"family_weights": risky, "baseline_weights": PRESETS.presets["Balanced"], "top": 20},
    ).json()
    assert len(p["top"]) == min(20, p["ranked"])
    assert all(row["move"] is not None for row in p["top"])
    assert p["elapsed_ms"] < 1000

    strict = client.post(
        "/scores/preview",
        json={"family_weights": risky, "gates": {**GATES, "min_mcap_crore": 9_000_000}},
    ).json()
    assert strict["passed"] == 0 and strict["top"] == []

    bad = client.post("/scores/preview", json={"family_weights": {**risky, "value": 11}})
    assert bad.status_code == 422
    missing = dict(risky)
    del missing["governance"]
    assert client.post("/scores/preview", json={"family_weights": missing}).status_code == 422

    profile = {"family_weights": risky, "gates": GATES, "agent_weights": PRESETS.agent_weights}
    assert client.put("/profiles/Mine", json=profile).status_code == 204
    assert [x["name"] for x in client.get("/profiles").json()] == ["Mine"]
    assert client.get("/scores", params={"profile": "Mine"}).json()["weights"] == risky
    assert client.get("/scores", params={"profile": "Nope"}).status_code == 404


@pytest.mark.integration
def test_presets_endpoint(client: TestClient) -> None:
    p = client.get("/presets").json()
    assert p["default"] == "Balanced" and len(p["families"]) == 7
    assert {f["key"] for f in p["factors"]} >= {"pe_vs_median", "governance_clean", "casa"}
