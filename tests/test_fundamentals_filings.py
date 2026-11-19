from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.ingest.filings import Filing, upsert_filings
from services.ingest.fundamentals import (
    FundamentalRow,
    fundamentals_as_of,
    monthly_call_budget,
    parse_fundamentals_csv,
    upsert_fundamentals,
)
from services.money import IST
from tests.conftest import FIXTURES
from tests.test_prices import _load_securities

Conn = psycopg.Connection[TupleRow]


def test_parse_converts_rupees_to_paise() -> None:
    rows = parse_fundamentals_csv(FIXTURES / "fundamentals.csv")
    assert rows[0].value == Decimal("24000050.00")
    assert rows[0].unit == "paise"
    assert rows[2].unit == "percent"


def test_available_from_cannot_precede_period_end() -> None:
    with pytest.raises(ValueError, match="before period end"):
        FundamentalRow(
            "INE002A01018",
            date(2026, 6, 30),
            "Q",
            "PL",
            "revenue",
            Decimal(1),
            "paise",
            datetime(2026, 6, 1, tzinfo=UTC),
        )


def test_monthly_call_budget() -> None:
    assert monthly_call_budget(5468, 1) == 23513
    assert monthly_call_budget(1300, 4) == 22360


@pytest.mark.integration
def test_point_in_time_hides_later_restatement(db: Conn) -> None:
    _load_securities(db)
    upsert_fundamentals(db, parse_fundamentals_csv(FIXTURES / "fundamentals.csv"), source="t")

    def revenue(as_of: datetime) -> Decimal | None:
        values = fundamentals_as_of(db, "INE002A01018", as_of)
        return next((v.value for v in values if v.field == "revenue"), None)

    assert revenue(datetime(2026, 7, 18, 15, 0, tzinfo=IST)) is None  # not yet public
    assert revenue(datetime(2026, 8, 1, tzinfo=IST)) == Decimal("24000050.00")
    assert revenue(datetime(2026, 10, 1, tzinfo=IST)) == Decimal("24100000.00")  # restated


@pytest.mark.integration
def test_filings_upsert_and_validation(db: Conn) -> None:
    _load_securities(db)
    filing = Filing(
        "INE002A01018",
        datetime(2026, 11, 18, 16, 0, tzinfo=IST),
        "results",
        "Q2 FY27 results",
        "https://www.bseindia.com/xml-data/corpfiling/AttachLive/example.pdf",
    )
    assert upsert_filings(db, [filing, filing], source="t") == 2
    assert db.execute("SELECT count(*) FROM filings").fetchone() == (1,)
    with pytest.raises(ValueError, match="https"):
        Filing("INE002A01018", filing.filed_at, "results", "x", "http://insecure.example/x.pdf")
