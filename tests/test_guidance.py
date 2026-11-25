import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.config import Settings
from services.ingest.transcripts import DocumentError, add_document, fetch_pdf
from services.llm.costs import BudgetExceeded, Usage, check_budget, cost_usd, record_usage
from services.mgmt_guidance.extract import (
    SCHEMA,
    collect,
    pending_documents,
    recheck,
    submit,
)
from services.mgmt_guidance.quote_check import canonical, check_quote, numbers_in
from tests.pdfgen import make_pdf
from tests.test_prices import _load_securities

Conn = psycopg.Connection[TupleRow]
NOW = datetime(2026, 11, 25, 6, 0, tzinfo=UTC)
PAGES = [
    "Opening remarks by the CFO.\n"
    "For FY27 we expect revenue growth of 15-18%,\ndriven by new capacity.",
    "On the investment side, capex will be about Rs 1,500 crore\n"
    "in FY27, funded from internal accruals.",
]
EN_DASH = chr(0x2013)
SETTINGS = Settings(_env_file=None)


# --- Quote check ---------------------------------------------------------------------


def test_quote_survives_line_breaks_and_typography() -> None:
    quote = f"For FY27 we expect revenue growth of 15{EN_DASH}18%, driven by new capacity."
    result = check_quote(quote, PAGES, [Decimal(15), Decimal(18)], claimed_page=1)
    assert result.verified and result.page_no == 1 and result.flag is None


def test_planted_paraphrase_is_rejected() -> None:
    quote = "For FY27 we expect sales growth of 15-18%, driven by new capacity."
    result = check_quote(quote, PAGES, [Decimal(15), Decimal(18)], claimed_page=1)
    assert not result.verified and result.flag == "quote not found in document"


def test_planted_wrong_number_is_rejected() -> None:
    quote = "capex will be about Rs 1,500 crore in FY27"
    result = check_quote(quote, PAGES, [Decimal(2000)], claimed_page=2)
    assert not result.verified and result.flag == "target 2000 not in quote"


def test_wrong_page_is_corrected_not_rejected() -> None:
    result = check_quote(
        "capex will be about Rs 1,500 crore", PAGES, [Decimal(1500)], claimed_page=1
    )
    assert result.verified and result.page_no == 2
    assert result.flag == "page corrected from 1 to 2"


def test_short_quote_cannot_verify() -> None:
    assert check_quote("15-18%", PAGES, [Decimal(15)]).flag == "quote too short to verify"


def test_numbers_and_units() -> None:
    assert numbers_in("Rs 1,500 crore and 15.5%") == {Decimal(1500), Decimal("15.5")}
    assert canonical(Decimal(1500), "inr_crore") == (Decimal(1500) * 10**9, "paise")
    assert canonical(Decimal(18), "percent") == (Decimal(18), "percent")


# --- Costs and budget --------------------------------------------------------------------


def test_haiku_batch_cost_and_long_context_rate() -> None:
    short = cost_usd(SETTINGS, "claude-haiku-5-5", Usage(20_000, 4_000), batch=True)
    assert short == Decimal("0.002000")  # (20k x 0.10 + 4k x 0.50) / 1M / 2
    long = cost_usd(SETTINGS, "claude-haiku-5-5", Usage(120_000, 4_000), batch=False)
    assert long == Decimal("0.070000")  # long rates: 0.50 in, 2.50 out
    with pytest.raises(KeyError):
        cost_usd(SETTINGS, "claude-unknown", Usage(1, 1), batch=False)


@pytest.mark.integration
def test_budget_caps_and_kill_switch(db: Conn) -> None:
    capped = Settings(_env_file=None, budget={"per_day_usd": 1.0, "per_month_usd": 2.0})
    check_budget(db, capped, Decimal("0.5"), now=NOW)
    record_usage(
        db,
        capped,
        purpose="t",
        request_ref="r",
        model_requested="claude-sonnet-5-5",
        model_served="claude-sonnet-5-5",
        usage=Usage(input_tokens=400_000),  # $0.80
        batch=False,
        at=NOW,
    )
    with pytest.raises(BudgetExceeded, match="daily cap"):
        check_budget(db, capped, Decimal("0.5"), now=NOW)
    with pytest.raises(BudgetExceeded, match="kill switch"):
        check_budget(db, Settings(_env_file=None, kill_switch=True), Decimal(0), now=NOW)


# --- Transcript ingest ---------------------------------------------------------------------


def test_exchange_sites_are_never_fetched() -> None:
    for url in (
        "https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf",
        "https://nsearchives.nseindia.com/corporate/x.pdf",
    ):
        with pytest.raises(DocumentError, match="Download the PDF yourself"):
            fetch_pdf(url)
    with pytest.raises(DocumentError, match="https"):
        fetch_pdf("http://ir.example.com/call.pdf")


@pytest.mark.integration
def test_add_document_stores_pages_once(db: Conn) -> None:
    _load_securities(db)
    pdf = make_pdf(PAGES)
    first = add_document(
        db, isin="INE002A01018", doc_type="TRANSCRIPT", doc_date=date(2026, 11, 10), pdf=pdf
    )
    again = add_document(
        db, isin="INE002A01018", doc_type="TRANSCRIPT", doc_date=date(2026, 11, 10), pdf=pdf
    )
    assert first.created and not again.created and first.document_id == again.document_id
    assert (first.pages, first.empty_pages) == (2, 0)
    with pytest.raises(DocumentError, match="unknown ISIN"):
        add_document(db, isin="INE000Z01019", doc_type="TRANSCRIPT", doc_date=NOW.date(), pdf=pdf)
    with pytest.raises(DocumentError, match="not a PDF"):
        add_document(db, isin="INE002A01018", doc_type="TRANSCRIPT", doc_date=NOW.date(), pdf=b"x")


# --- Extraction -----------------------------------------------------------------------


def _row(quote: str, low: float, high: float, unit: str, page: int, metric: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "metric_detail": "",
        "target_period": "FY27",
        "target_low": low,
        "target_high": high,
        "unit": unit,
        "quote": quote,
        "page": page,
    }


GOOD = _row(
    "For FY27 we expect revenue growth of 15-18%, driven by new capacity.",
    15,
    18,
    "percent",
    1,
    "REVENUE_GROWTH",
)
PARAPHRASED = _row("Revenue will grow 15-18% next year.", 15, 18, "percent", 1, "REVENUE_GROWTH")
WRONG_NUMBER = _row(
    "capex will be about Rs 1,500 crore in FY27", 2000, 2000, "inr_crore", 2, "CAPEX"
)


def _message(text: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        model="claude-haiku-5-5",
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=2_000,
            output_tokens=500,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


class FakeBatches:
    def __init__(self) -> None:
        self.status = "in_progress"
        self.requests: list[dict[str, Any]] = []
        self.replies: dict[str, SimpleNamespace] = {}

    def create(self, *, requests: list[dict[str, Any]]) -> SimpleNamespace:
        self.requests = requests
        return SimpleNamespace(id="msgbatch_test1")

    def retrieve(self, batch_id: str) -> SimpleNamespace:
        return SimpleNamespace(processing_status=self.status)

    def results(self, batch_id: str) -> Iterator[SimpleNamespace]:
        for req in self.requests:
            yield SimpleNamespace(custom_id=req["custom_id"], result=self.replies[req["custom_id"]])


def _load_doc(db: Conn) -> int:
    _load_securities(db)
    return add_document(
        db,
        isin="INE002A01018",
        doc_type="TRANSCRIPT",
        doc_date=date(2026, 11, 10),
        pdf=make_pdf(PAGES),
        period_label="Q2FY27",
    ).document_id


@pytest.mark.integration
def test_submit_builds_a_compliant_batch_request(db: Conn) -> None:
    _load_doc(db)
    fake = FakeBatches()
    result = submit(db, fake, SETTINGS, now=NOW)
    assert result.requests == 1 and result.batch_id == "msgbatch_test1"
    assert Decimal(0) < result.estimate_usd < Decimal("0.01")
    params = fake.requests[0]["params"]
    assert params["model"] == "claude-haiku-5-5"
    assert params["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }
    for banned in ("temperature", "top_p", "top_k", "tool_choice", "tools"):
        assert banned not in params
    assert '<page n="2">' in params["messages"][0]["content"]
    assert pending_documents(db) == []  # in flight, so not resubmitted


@pytest.mark.integration
def test_submit_refuses_over_budget(db: Conn) -> None:
    _load_doc(db)
    fake = FakeBatches()
    tiny = Settings(_env_file=None, budget={"per_day_usd": 0.000001, "per_month_usd": 1.0})
    with pytest.raises(BudgetExceeded):
        submit(db, fake, tiny, now=NOW)
    assert fake.requests == []  # nothing was sent


@pytest.mark.integration
def test_collect_verifies_good_rows_and_flags_planted_ones(db: Conn) -> None:
    _load_doc(db)
    fake = FakeBatches()
    submit(db, fake, SETTINGS, now=NOW)
    assert collect(db, fake, SETTINGS, now=NOW).batches_pending == 1

    fake.status = "ended"
    custom_id = fake.requests[0]["custom_id"]
    body = json.dumps({"rows": [GOOD, PARAPHRASED, WRONG_NUMBER]})
    fake.replies[custom_id] = SimpleNamespace(type="succeeded", message=_message(body))
    out = collect(db, fake, SETTINGS, now=NOW)
    assert (out.succeeded, out.rows, out.verified) == (1, 3, 1)
    assert out.cost_usd == Decimal("0.000225")  # (2k x 0.10 + 500 x 0.50) / 1M / 2

    rows = db.execute(
        "SELECT quote, status, flag, target_low, unit FROM mgmt_guidance ORDER BY id"
    ).fetchall()
    assert [(r[1], r[2]) for r in rows] == [
        ("QUOTE_VERIFIED", None),
        ("EXTRACTED", "quote not found in document"),
        ("EXTRACTED", "target 2000 not in quote"),
    ]
    assert rows[2][3:] == (Decimal(2000) * 10**9, "paise")
    run = db.execute("SELECT status, model_served, raw_output FROM extraction_runs").fetchone()
    assert run is not None and run[0] == "SUCCEEDED" and run[1] == "claude-haiku-5-5"
    assert run[2] == body  # raw output kept for audit
    assert recheck(db) == (2, 0)  # planted rows stay flagged


@pytest.mark.integration
@pytest.mark.parametrize(
    ("reply", "status"),
    [
        (SimpleNamespace(type="succeeded", message=_message("", "refusal")), "REFUSED"),
        (SimpleNamespace(type="succeeded", message=_message('{"rows": [', "max_tokens")), "FAILED"),
        (SimpleNamespace(type="succeeded", message=_message('{"rows": "x"}')), "FAILED"),
        (SimpleNamespace(type="errored", error=SimpleNamespace(type="api_error")), "FAILED"),
    ],
)
def test_collect_handles_bad_outcomes(db: Conn, reply: SimpleNamespace, status: str) -> None:
    _load_doc(db)
    fake = FakeBatches()
    submit(db, fake, SETTINGS, now=NOW)
    fake.status = "ended"
    fake.replies[fake.requests[0]["custom_id"]] = reply
    collect(db, fake, SETTINGS, now=NOW)
    assert db.execute("SELECT status FROM extraction_runs").fetchone() == (status,)
    assert db.execute("SELECT count(*) FROM mgmt_guidance").fetchone() == (0,)
    if status == "FAILED":
        assert len(pending_documents(db)) == 1  # failed documents can be resubmitted
