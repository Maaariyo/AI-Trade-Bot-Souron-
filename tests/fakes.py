"""A fake Kite client with responses shaped like kiteconnect's parsed output."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def instrument(
    token: int, exchange: str, symbol: str, exchange_token: str, *, segment: str | None = None
) -> dict[str, Any]:
    seg = segment or exchange
    return {
        "instrument_token": token,
        "exchange_token": exchange_token,
        "tradingsymbol": symbol,
        "name": symbol,
        "last_price": 0.0,
        "expiry": "",
        "strike": 0.0,
        "tick_size": 0.05,
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": seg,
        "exchange": exchange,
    }


def candle(day: date, o: float, h: float, low: float, c: float, v: int) -> dict[str, Any]:
    return {
        "date": datetime(day.year, day.month, day.day, tzinfo=IST_OFFSET),
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
    }


class FakeKite:
    def __init__(
        self,
        instruments: dict[str, list[dict[str, Any]]] | None = None,
        candles: dict[int, list[dict[str, Any]]] | None = None,
        errors: dict[int, Exception] | None = None,
    ) -> None:
        self._instruments = instruments or {}
        self._candles = candles or {}
        self._errors = errors or {}
        self.calls: list[tuple[int, date, date]] = []
        self.access_token: str | None = None

    def login_url(self) -> str:
        return "https://kite.zerodha.com/connect/login?api_key=test&v=3"

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, Any]:
        assert request_token == "req-ok" and api_secret == "secret"
        return {"access_token": "tok-123", "user_id": "AB1234", "login_time": None}

    def set_access_token(self, access_token: str) -> None:
        self.access_token = access_token

    def instruments(self, exchange: str | None = None) -> list[dict[str, Any]]:
        return self._instruments.get(exchange or "", [])

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime | date | str,
        to_date: datetime | date | str,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]:
        assert interval == "day"
        assert isinstance(from_date, date) and isinstance(to_date, date)
        self.calls.append((instrument_token, from_date, to_date))
        if instrument_token in self._errors:
            raise self._errors[instrument_token]
        return [
            c
            for c in self._candles.get(instrument_token, [])
            if from_date <= c["date"].date() <= to_date
        ]
