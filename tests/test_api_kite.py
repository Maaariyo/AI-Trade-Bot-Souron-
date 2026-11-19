from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import TupleRow

import services.api.kite as kite_api
from services.api.main import app
from services.config import Settings
from services.db import connect
from tests.fakes import FakeKite

Conn = psycopg.Connection[TupleRow]
NOW = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, schema_url: str, db: Conn) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, kite_api_key="test", kite_api_secret="secret")
    monkeypatch.setattr(kite_api, "connect", lambda **kw: connect(schema_url, **kw))
    monkeypatch.setattr(kite_api, "get_settings", lambda: settings)
    app.dependency_overrides[kite_api.kite_client_factory] = lambda: lambda s: FakeKite()
    app.dependency_overrides[kite_api.utcnow] = lambda: NOW
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_login_redirects_to_zerodha(client: TestClient) -> None:
    r = client.get("/kite/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://kite.zerodha.com/connect/login")


@pytest.mark.integration
def test_callback_connects_and_never_returns_the_token(client: TestClient) -> None:
    assert client.get("/kite/status").json() == {"connected": False, "expires_at": None}
    r = client.get("/kite/callback", params={"request_token": "req-ok", "status": "success"})
    assert r.status_code == 200
    assert "19-Nov-2026 06:00 IST" in r.text
    assert "tok-123" not in r.text
    status: dict[str, Any] = client.get("/kite/status").json()
    assert status["connected"] is True
    assert "tok-123" not in str(status)


@pytest.mark.integration
def test_failed_login_is_rejected(client: TestClient) -> None:
    r = client.get("/kite/callback", params={"request_token": "x", "status": "cancelled"})
    assert r.status_code == 400


@pytest.mark.integration
def test_alerts_lists_open_alerts(client: TestClient, db: Conn) -> None:
    db.execute("INSERT INTO alerts (kind, message) VALUES ('kite_not_connected', 'log in')")
    assert [a["kind"] for a in client.get("/alerts").json()] == ["kite_not_connected"]


@pytest.mark.integration
def test_login_without_api_key_is_503(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    blank = Settings(_env_file=None, kite_api_key="", kite_api_secret="")
    monkeypatch.setattr(kite_api, "get_settings", lambda: blank)
    app.dependency_overrides.pop(kite_api.kite_client_factory)
    r = client.get("/kite/login", follow_redirects=False)
    assert r.status_code == 503
    assert "KITE_API_KEY" in r.json()["detail"]
