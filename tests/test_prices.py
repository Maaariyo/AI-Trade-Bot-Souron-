from datetime import UTC, date, datetime

import psycopg
import pytest
from kiteconnect import exceptions as kex
from psycopg.rows import TupleRow

from services.config import Settings
from services.ingest.kite_auth import complete_login, current_access_token, session_status
from services.ingest.prices import (
    Candle,
    RateLimiter,
    candles_from_kite,
    date_chunks,
    ingest_daily_prices,
    ingest_index_prices,
    price_targets,
    refresh_instruments,
    years_before,
)
from services.ingest.security_master import (
    merge_listings,
    parse_bse_list,
    parse_nse_list,
    upsert_securities,
)
from services.money import IST, next_ist_time, to_paise
from tests.conftest import FIXTURES
from tests.fakes import FakeKite, candle, instrument

Conn = psycopg.Connection[TupleRow]
TODAY = date(2026, 11, 18)


def test_to_paise_avoids_float_error() -> None:
    assert to_paise(2456.35) == 245635
    assert to_paise("0.05") == 5
    assert to_paise(0.125) == 13  # half up


def test_kite_token_expires_at_next_six_am_ist() -> None:
    six = Settings(_env_file=None).kite.token_expiry_ist
    morning = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)  # 08:30 IST
    assert next_ist_time(morning, six) == datetime(2026, 11, 19, 6, 0, tzinfo=IST)
    early = datetime(2026, 11, 17, 23, 0, tzinfo=UTC)  # 04:30 IST
    assert next_ist_time(early, six) == datetime(2026, 11, 18, 6, 0, tzinfo=IST)


def test_candles_convert_to_ist_dates_and_paise() -> None:
    [c] = candles_from_kite([candle(TODAY, 100.05, 102.5, 99.95, 101.1, 1200)])
    assert c == Candle(TODAY, 10005, 10250, 9995, 10110, 1200)
    assert c.is_valid()
    assert c.estimated_value_paise == ((10250 + 9995 + 10110) // 3) * 1200
    assert not Candle(TODAY, 10300, 10250, 9995, 10110, 1).is_valid()  # open above high


def test_date_chunks_and_leap_day() -> None:
    chunks = list(date_chunks(date(2020, 1, 1), date(2020, 1, 10), 4))
    assert chunks == [
        (date(2020, 1, 1), date(2020, 1, 4)),
        (date(2020, 1, 5), date(2020, 1, 8)),
        (date(2020, 1, 9), date(2020, 1, 10)),
    ]
    assert years_before(date(2028, 2, 29), 5) == date(2023, 2, 28)


def test_rate_limiter_spaces_calls() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(4.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.wait()
    assert slept == [0.25, 0.25]


def _load_securities(db: Conn) -> None:
    snapshot = [
        *parse_nse_list(FIXTURES / "nse_equity_l.csv", is_sme=False),
        *parse_nse_list(FIXTURES / "nse_sme_equity_l.csv", is_sme=True),
        *parse_bse_list(FIXTURES / "bse_scrips.csv"),
    ]
    upsert_securities(db, merge_listings(snapshot), as_of=TODAY, source="t")


def _fake() -> FakeKite:
    return FakeKite(
        instruments={
            "NSE": [
                instrument(738561, "NSE", "RELIANCE", "2885"),
                instrument(408065, "NSE", "INFY", "1594"),
                instrument(111111, "NSE", "NSEONLY-BE", "9999"),
                instrument(256265, "NSE", "NIFTY 50", "26000", segment="INDICES"),
            ],
            "BSE": [
                instrument(128083204, "BSE", "RELIANCE", "500325"),
                instrument(139264004, "BSE", "BSESME", "544000"),
            ],
        },
        candles={
            738561: [
                candle(date(2026, 11, 17), 2400, 2420, 2390, 2410.5, 5_000_000),
                candle(TODAY, 2410, 2450.25, 2405, 2440, 6_000_000),
            ],
            139264004: [candle(TODAY, 50, 52, 49.5, 51, 8000)],
            256265: [candle(TODAY, 24000, 24100.5, 23950, 24050.25, 0)],
        },
        errors={408065: kex.DataException("no data")},
    )


@pytest.mark.integration
def test_refresh_instruments_maps_isins(db: Conn) -> None:
    _load_securities(db)
    result = refresh_instruments(db, _fake(), as_of=TODAY)
    assert (result.instruments, result.mapped) == (6, 5)
    targets = {t.isin: (t.exchange, t.instrument_token) for t in price_targets(db, as_of=TODAY)}
    assert targets["INE002A01018"] == ("NSE", 738561)  # NSE preferred over BSE
    assert targets["INE111A01019"] == ("NSE", 111111)  # "-BE" suffix mapped
    assert targets["INE444D01018"] == ("BSE", 139264004)  # BSE by scrip code
    assert "INE333C01015" not in targets  # suspended


@pytest.mark.integration
def test_ingest_is_incremental_and_records_failures(db: Conn) -> None:
    _load_securities(db)
    kite = _fake()
    refresh_instruments(db, kite, as_of=TODAY)
    limiter = RateLimiter(1000.0)
    first = ingest_daily_prices(
        db,
        kite,
        price_targets(db, as_of=TODAY),
        today=TODAY,
        history_years=5,
        max_days_per_request=1900,
        limiter=limiter,
    )
    assert first.rows == 3
    assert set(first.failures) == {"INE009A01021"}
    assert (738561, date(2021, 11, 18), TODAY) in kite.calls  # 5 years, one request

    row = db.execute(
        "SELECT close_paise, volume, value_is_estimate FROM daily_prices "
        "WHERE isin = 'INE002A01018' AND trade_date = %s",
        (TODAY,),
    ).fetchone()
    assert row == (244000, 6_000_000, True)

    kite.calls.clear()
    second = ingest_daily_prices(
        db,
        kite,
        price_targets(db, as_of=TODAY),
        today=TODAY,
        history_years=5,
        max_days_per_request=1900,
        limiter=limiter,
    )
    assert (738561, TODAY, TODAY) in kite.calls  # starts at the last stored day
    assert second.rebased == []
    assert db.execute("SELECT count(*) FROM daily_prices").fetchone() == (3,)  # no duplicates


@pytest.mark.integration
def test_upstream_readjustment_triggers_full_refetch(db: Conn) -> None:
    _load_securities(db)
    kite = _fake()
    refresh_instruments(db, kite, as_of=TODAY)
    limiter = RateLimiter(1000.0)
    args = {"today": TODAY, "history_years": 5, "max_days_per_request": 1900, "limiter": limiter}
    ingest_daily_prices(db, kite, price_targets(db, as_of=TODAY), **args)  # type: ignore[arg-type]

    # A 1:2 split: Kite now serves every past candle at half the price.
    kite._candles[738561] = [
        candle(date(2026, 11, 17), 1200, 1210, 1195, 1205.25, 10_000_000),
        candle(TODAY, 1205, 1225.15, 1202.5, 1220, 12_000_000),
    ]
    result = ingest_daily_prices(db, kite, price_targets(db, as_of=TODAY), **args)  # type: ignore[arg-type]
    assert result.rebased == ["INE002A01018"]
    closes = db.execute(
        "SELECT trade_date, close_paise FROM daily_prices WHERE isin = 'INE002A01018' "
        "ORDER BY trade_date"
    ).fetchall()
    assert closes == [(date(2026, 11, 17), 120525), (TODAY, 122000)]


@pytest.mark.integration
def test_token_error_stops_the_run(db: Conn) -> None:
    _load_securities(db)
    kite = _fake()
    kite._errors[738561] = kex.TokenException("expired")
    refresh_instruments(db, kite, as_of=TODAY)
    with pytest.raises(kex.TokenException):
        ingest_daily_prices(
            db,
            kite,
            price_targets(db, as_of=TODAY),
            today=TODAY,
            history_years=5,
            max_days_per_request=1900,
            limiter=RateLimiter(1000.0),
        )


@pytest.mark.integration
def test_index_prices(db: Conn) -> None:
    _load_securities(db)
    kite = _fake()
    refresh_instruments(db, kite, as_of=TODAY)
    rows, missing = ingest_index_prices(
        db,
        kite,
        ["NIFTY 50", "NIFTY 500"],
        as_of=TODAY,
        today=TODAY,
        history_years=5,
        max_days_per_request=1900,
        limiter=RateLimiter(1000.0),
    )
    assert (rows, missing) == (1, ["NIFTY 500"])


@pytest.mark.integration
def test_login_stores_session_and_resolves_alert(db: Conn) -> None:
    db.execute("INSERT INTO alerts (kind, message) VALUES ('kite_not_connected', 'log in')")
    settings = Settings(
        _env_file=None,
        kite_api_key="test",
        kite_api_secret="secret",
    )
    now = datetime(2026, 11, 18, 3, 0, tzinfo=UTC)
    expires = complete_login(db, FakeKite(), settings, "req-ok", now=now)
    assert expires == datetime(2026, 11, 19, 6, 0, tzinfo=IST)
    assert current_access_token(db, now=now) == "tok-123"
    assert current_access_token(db, now=expires) is None
    assert session_status(db, now=now).connected
    open_kinds = db.execute("SELECT kind FROM alerts WHERE resolved_at IS NULL").fetchall()
    assert open_kinds == []
