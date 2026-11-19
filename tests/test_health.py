from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import TupleRow

import services.api.main as api
from services.db import connect
from services.migrate import apply_migrations
from services.worker.main import record_heartbeat


def test_health_degraded_without_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: Any, **__: Any) -> None:
        raise psycopg.OperationalError("no database")

    monkeypatch.setattr(api, "connect", broken)
    body = TestClient(api.app).get("/health").json()
    assert body["status"] == "degraded"
    assert body["db"] == "unavailable"
    assert body["worker_last_heartbeat"] is None


@pytest.mark.integration
def test_health_reports_worker_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    schema_url: str,
    schema_conn: psycopg.Connection[TupleRow],
) -> None:
    apply_migrations(schema_conn)
    monkeypatch.setattr(api, "connect", lambda **kw: connect(schema_url, **kw))
    client = TestClient(api.app)

    before = client.get("/health").json()
    assert before["status"] == "ok"
    assert before["worker_last_heartbeat"] is None

    record_heartbeat(schema_url)
    after = client.get("/health").json()
    assert after["db"] == "ok"
    assert after["worker_last_heartbeat"] is not None
