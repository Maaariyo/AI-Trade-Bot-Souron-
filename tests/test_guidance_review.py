import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import TupleRow

import services.api.guidance as guidance_api
from services.api.main import app
from services.db import connect
from services.mgmt_guidance.extract import collect, submit
from services.mgmt_guidance.review import ReviewError, add_manual, review_stats, usable_guidance
from tests.test_guidance import GOOD, PARAPHRASED, SETTINGS, FakeBatches, _load_doc, _message

Conn = psycopg.Connection[TupleRow]
NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)


def _extract(db: Conn) -> int:
    doc_id = _load_doc(db)
    fake = FakeBatches()
    submit(db, fake, SETTINGS, now=NOW)
    fake.status = "ended"
    body = json.dumps({"rows": [GOOD, PARAPHRASED]})
    fake.replies[fake.requests[0]["custom_id"]] = SimpleNamespace(
        type="succeeded", message=_message(body)
    )
    collect(db, fake, SETTINGS, now=NOW)
    return doc_id


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, schema_url: str, db: Conn) -> Iterator[TestClient]:
    monkeypatch.setattr(guidance_api, "connect", lambda **kw: connect(schema_url, **kw))
    app.dependency_overrides[guidance_api.utcnow] = lambda: NOW
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_only_verified_or_reviewed_rows_are_usable(db: Conn) -> None:
    _extract(db)
    usable = usable_guidance(db, "INE002A01018")
    assert [u.status for u in usable] == ["QUOTE_VERIFIED"]  # the paraphrase is held back


@pytest.mark.integration
def test_review_flow_over_the_api(client: TestClient, db: Conn) -> None:
    _extract(db)
    rows = {r["status"]: r for r in client.get("/guidance").json()}
    verified, flagged = rows["QUOTE_VERIFIED"], rows["EXTRACTED"]

    assert client.post(f"/guidance/{verified['id']}/approve", json={}).status_code == 204
    r = client.post(f"/guidance/{flagged['id']}/approve", json={})
    assert r.status_code == 409 and "add a note" in r.json()["detail"]
    assert (
        client.post(f"/guidance/{flagged['id']}/reject", json={"note": "paraphrase"}).status_code
        == 204
    )
    again = client.post(f"/guidance/{verified['id']}/reject", json={})
    assert again.status_code == 409  # already reviewed

    stats = client.get("/guidance/stats").json()
    assert stats["by_status"] == {"HUMAN_REVIEWED": 1, "REJECTED": 1}
    assert (stats["verified_reviewed"], stats["verified_approved"], stats["agreement"]) == (
        1,
        1,
        1.0,
    )


@pytest.mark.integration
def test_manual_rows_must_pass_the_quote_check(client: TestClient, db: Conn) -> None:
    doc_id = _load_doc(db)
    good = {
        "document_id": doc_id,
        "metric": "CAPEX",
        "target_period": "FY27",
        "target_low": 1500,
        "target_high": 1500,
        "unit": "inr_crore",
        "quote": "capex will be about Rs 1,500 crore in FY27",
    }
    r = client.post("/guidance/manual", json=good)
    assert r.status_code == 201
    row = db.execute(
        "SELECT method, status, page_no, target_low, unit FROM mgmt_guidance WHERE id = %s",
        (r.json()["id"],),
    ).fetchone()
    assert row == ("manual", "HUMAN_REVIEWED", 2, Decimal(1500) * 10**9, "paise")

    bad = {**good, "target_low": 1600, "target_high": 1600}
    r = client.post("/guidance/manual", json=bad)
    assert r.status_code == 422 and "not in quote" in r.json()["detail"]
    with pytest.raises(ReviewError, match="no document"):
        add_manual(
            db,
            document_id=999,
            metric="CAPEX",
            target_period="FY27",
            target_low=Decimal(1),
            target_high=Decimal(1),
            unit="inr_crore",
            quote="x" * 20,
            now=NOW,
        )
    assert review_stats(db).by_status == {"HUMAN_REVIEWED": 1}
