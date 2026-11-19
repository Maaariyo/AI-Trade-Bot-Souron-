"""Kite Connect sessions from the owner's manual daily login.

CLAUDE.md non-negotiable 5: never automate the login. The owner opens
/kite/login, signs in on Zerodha's page with 2FA, and Zerodha redirects to
/kite/callback with a request token, which is exchanged here for an access
token. Tokens stay in Postgres on the server and are never sent to the browser.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

import psycopg
from psycopg.rows import TupleRow
from pydantic import SecretStr

from services.alerts import KITE_NOT_CONNECTED, resolve_alert
from services.config import Settings
from services.money import next_ist_time

BROKER = "kite"


class KiteClient(Protocol):
    """The subset of kiteconnect.KiteConnect this app uses (and the test fakes implement)."""

    def login_url(self) -> str: ...

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, Any]: ...

    def set_access_token(self, access_token: str) -> None: ...

    def instruments(self, exchange: str | None = None) -> list[dict[str, Any]]: ...

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime | date | str,
        to_date: datetime | date | str,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]: ...


class KiteNotConfigured(RuntimeError):
    pass


def _secret(value: SecretStr | None, name: str) -> str:
    """The secret's value; an unset or empty setting raises KiteNotConfigured."""
    if value is None or not value.get_secret_value().strip():
        raise KiteNotConfigured(f"{name} is not set in .env")
    return value.get_secret_value().strip()


def make_client(settings: Settings, access_token: str | None = None) -> KiteClient:
    api_key = _secret(settings.kite_api_key, "KITE_API_KEY")
    from kiteconnect import KiteConnect

    client: KiteClient = KiteConnect(api_key=api_key)
    if access_token:
        client.set_access_token(access_token)
    return client


def complete_login(
    conn: psycopg.Connection[TupleRow],
    client: KiteClient,
    settings: Settings,
    request_token: str,
    *,
    now: datetime,
) -> datetime:
    """Exchange the request token, store the session, and return when it expires."""
    api_secret = _secret(settings.kite_api_secret, "KITE_API_SECRET")
    session = client.generate_session(request_token, api_secret)
    expires_at = next_ist_time(now, settings.kite.token_expiry_ist)
    conn.execute(
        "INSERT INTO broker_sessions (broker, access_token, user_id, login_time, expires_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (BROKER, session["access_token"], session.get("user_id"), now, expires_at),
    )
    resolve_alert(conn, KITE_NOT_CONNECTED)
    return expires_at


def current_access_token(conn: psycopg.Connection[TupleRow], *, now: datetime) -> str | None:
    row = conn.execute(
        "SELECT access_token FROM broker_sessions WHERE broker = %s AND expires_at > %s "
        "ORDER BY login_time DESC LIMIT 1",
        (BROKER, now),
    ).fetchone()
    return row[0] if row else None


@dataclass(frozen=True)
class SessionStatus:
    connected: bool
    expires_at: datetime | None


def session_status(conn: psycopg.Connection[TupleRow], *, now: datetime) -> SessionStatus:
    row = conn.execute(
        "SELECT expires_at FROM broker_sessions WHERE broker = %s AND expires_at > %s "
        "ORDER BY login_time DESC LIMIT 1",
        (BROKER, now),
    ).fetchone()
    return SessionStatus(connected=row is not None, expires_at=row[0] if row else None)
