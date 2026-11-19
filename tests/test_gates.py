from datetime import date, timedelta

import psycopg
import pytest
from psycopg.rows import TupleRow

from services.factors.gates import CRORE_PAISE, PriceGateConfig, price_gate_results
from services.ingest.prices import Candle, upsert_candles
from tests.test_prices import _load_securities

Conn = psycopg.Connection[TupleRow]
AS_OF = date(2026, 11, 18)


def _days(n: int) -> list[date]:
    return [AS_OF - timedelta(days=i) for i in range(n)]


def _candles(days: list[date], close_paise: int, volume: int) -> list[Candle]:
    return [Candle(d, close_paise, close_paise, close_paise, close_paise, volume) for d in days]


@pytest.mark.integration
def test_price_gates(db: Conn) -> None:
    _load_securities(db)
    # Reliance: Rs 2,440 x 6,00,000 shares = Rs 146 crore a day.
    upsert_candles(db, "INE002A01018", "NSE", _candles(_days(60), 244_000, 600_000))
    # NSEONLY: Rs 10 x 1,00,000 = Rs 10 lakh a day, and under GSM.
    upsert_candles(db, "INE111A01019", "NSE", _candles(_days(60), 1_000, 100_000))
    db.execute("UPDATE securities SET surveillance = 'GSM' WHERE isin = 'INE111A01019'")
    # Infosys: liquid but only 10 days of prices.
    upsert_candles(db, "INE009A01021", "NSE", _candles(_days(10), 150_000, 1_000_000))

    results = {r.isin: r for r in price_gate_results(db, as_of=AS_OF)}
    assert results["INE002A01018"].passed
    assert results["INE002A01018"].median_value_paise == 244_000 * 600_000
    assert results["INE111A01019"].reasons == [
        "under GSM",
        "median traded value below Rs 5 crore",
    ]
    assert results["INE009A01021"].reasons == ["only 10 trading days of prices"]
    assert results["INE333C01015"].reasons[0] == "status SUSPENDED"

    lenient = PriceGateConfig(min_median_value_paise=CRORE_PAISE // 100, exclude_gsm=False)
    assert {r.isin for r in price_gate_results(db, as_of=AS_OF, cfg=lenient) if r.passed} == {
        "INE002A01018",
        "INE111A01019",
    }
