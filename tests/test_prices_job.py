from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.alerts import open_alerts
from services.config import Settings
from services.ingest.kite_auth import KiteClient, complete_login
from services.worker.prices_job import run_prices
from tests.fakes import FakeKite
from tests.test_prices import _fake, _load_securities

Conn = psycopg.Connection[TupleRow]
SETTINGS = Settings(
    _env_file=None,
    kite_api_key="test",
    kite_api_secret="secret",
    kite={"index_codes": ["NIFTY 50"], "historical_requests_per_second": 1000.0},
)
EVENING = datetime(2026, 11, 18, 13, 0, tzinfo=UTC)  # 18:30 IST
LATE = datetime(2026, 11, 18, 17, 30, tzinfo=UTC)  # 23:00 IST


def _kinds(db: Conn) -> set[str]:
    return {a.kind for a in open_alerts(db)}


@pytest.mark.integration
def test_waits_then_skips_without_a_session(db: Conn) -> None:
    def factory(s: Settings, token: str) -> KiteClient:
        raise AssertionError("must not call Kite without a session")

    assert run_prices(db, SETTINGS, now=EVENING, client_factory=factory) == "waiting"
    assert _kinds(db) == {"kite_not_connected"}
    assert run_prices(db, SETTINGS, now=LATE, client_factory=factory) == "skipped"
    assert "price_run_skipped" in _kinds(db)
    assert run_prices(db, SETTINGS, now=LATE, client_factory=factory) == "done-already"


@pytest.mark.integration
def test_runs_once_with_a_session(db: Conn) -> None:
    _load_securities(db)
    kite = _fake()
    complete_login(db, FakeKite(), SETTINGS, "req-ok", now=datetime(2026, 11, 18, 3, 0, tzinfo=UTC))
    outcome = run_prices(db, SETTINGS, now=EVENING, client_factory=lambda s, t: kite)
    assert outcome == "succeeded"
    assert _kinds(db) == set()
    count = db.execute("SELECT count(*) FROM daily_prices").fetchone()
    assert count is not None and count[0] == 3
    status = db.execute(
        "SELECT status FROM job_runs WHERE job_name = 'prices' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert status == ("succeeded",)
    assert run_prices(db, SETTINGS, now=LATE, client_factory=lambda s, t: kite) == "done-already"
