from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.ingest.benchmark import (
    BenchmarkPoint,
    approximate_tri,
    parse_tri_csv,
    upsert_benchmark,
)
from services.ingest.corporate_actions import (
    CorporateAction,
    parse_actions_csv,
    total_return_index,
    upsert_actions,
)
from tests.conftest import FIXTURES
from tests.test_prices import _load_securities

Conn = psycopg.Connection[TupleRow]
D0, D1, D2 = date(2026, 8, 12), date(2026, 8, 13), date(2026, 8, 14)
ANNOUNCED = datetime(2026, 7, 1, tzinfo=UTC)


def _split(day: date, before: int, after: int) -> CorporateAction:
    return CorporateAction(
        "INE009A01021", "SPLIT", day, ANNOUNCED, shares_before=before, shares_after=after
    )


def _dividend(day: date, paise: int) -> CorporateAction:
    return CorporateAction("INE009A01021", "DIVIDEND", day, ANNOUNCED, cash_paise_per_share=paise)


def test_parse_actions_csv() -> None:
    div, split = parse_actions_csv(FIXTURES / "corporate_actions.csv")
    assert div.cash_paise_per_share == 1000
    assert split.share_factor == 5


def test_actions_need_time_zone_and_ratio() -> None:
    with pytest.raises(ValueError, match="time zone"):
        CorporateAction(
            "INE009A01021", "DIVIDEND", D1, datetime(2026, 7, 1), cash_paise_per_share=1
        )
    with pytest.raises(ValueError, match="ratio"):
        CorporateAction("INE009A01021", "SPLIT", D1, ANNOUNCED)


def test_total_return_unadjusted_prices() -> None:
    # A 1:5 split with the price falling 10,000 -> 2,000 paise is no loss.
    tri = total_return_index(
        [(D0, 10_000), (D1, 2_000)], [_split(D1, 1, 5)], prices_split_adjusted=False
    )
    assert tri[-1][1] == 100
    # A 100-paise dividend offsets a 100-paise ex-date drop.
    tri = total_return_index(
        [(D0, 10_000), (D1, 9_900)], [_dividend(D1, 100)], prices_split_adjusted=False
    )
    assert tri[-1][1] == 100


def test_total_return_split_adjusted_prices() -> None:
    # Prices already divided by a later 1:5 split, so the dividend is scaled too: 100 / 5 = 20.
    closes = [(D0, 2_000), (D1, 1_980), (D2, 1_990)]
    tri = total_return_index(
        closes, [_dividend(D1, 100), _split(D2, 1, 5)], prices_split_adjusted=True
    )
    assert tri[1][1] == 100
    assert tri[2][1] == Decimal(100) * Decimal(1_990) / Decimal(1_980)


def test_parse_tri_csv_sorts_and_strips_commas() -> None:
    points = parse_tri_csv(FIXTURES / "nifty500_tri.csv")
    assert points == [
        BenchmarkPoint(date(2026, 11, 17), Decimal("38301.55")),
        BenchmarkPoint(date(2026, 11, 18), Decimal("38450.12")),
    ]


def test_approximate_tri_adds_yield_once_a_month() -> None:
    index = [
        (date(2026, 10, 30), Decimal(100)),
        (date(2026, 11, 2), Decimal(101)),
        (date(2026, 11, 3), Decimal(102)),
    ]
    points = approximate_tri(index, {(2026, 11): Decimal("1.2")})
    assert [p.value for p in points] == [
        Decimal("100.0000"),
        Decimal("101.1010"),
        Decimal("102.1020"),
    ]


@pytest.mark.integration
def test_upserts(db: Conn) -> None:
    _load_securities(db)
    assert (
        upsert_actions(db, parse_actions_csv(FIXTURES / "corporate_actions.csv"), source="t") == 2
    )
    assert (
        upsert_actions(db, parse_actions_csv(FIXTURES / "corporate_actions.csv"), source="t") == 2
    )
    count = db.execute("SELECT count(*) FROM corporate_actions").fetchone()
    assert count == (2,)

    day = date(2026, 11, 18)
    upsert_benchmark(db, [BenchmarkPoint(day, Decimal(500))], is_approximate=False, source="nse")
    upsert_benchmark(db, [BenchmarkPoint(day, Decimal(1))], is_approximate=True, source="approx")
    row = db.execute("SELECT value, is_approximate FROM benchmark_values").fetchone()
    assert row == (Decimal(500), False)  # licensed value kept
