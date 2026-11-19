"""Nightly price update (SPEC section 4, "Kite daily login").

Runs at 18:30 IST on weekdays and retries hourly. It needs a Kite session
from the owner's manual login that day; without one it raises a dashboard
alert and waits. If there is still no session at 23:00 IST, the run is
recorded as skipped.
"""

import json
from collections.abc import Callable
from datetime import datetime, time

import psycopg
from psycopg.rows import TupleRow

from services.alerts import KITE_NOT_CONNECTED, PRICE_RUN_SKIPPED, raise_alert, resolve_alert
from services.config import Settings
from services.ingest.kite_auth import KiteClient, current_access_token
from services.ingest.prices import (
    RateLimiter,
    ingest_daily_prices,
    ingest_index_prices,
    price_targets,
    refresh_instruments,
)
from services.money import IST, ist_date
from services.worker.runs import finish_run, has_run_on, record_run, start_run

JOB = "prices"
FINAL_ATTEMPT = time(23, 0)
SCHEDULE_HOURS_MINUTES = [(18, 30), (19, 30), (20, 30), (21, 30), (22, 30), (23, 0)]

ClientFactory = Callable[[Settings, str], KiteClient]


def run_prices(
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    *,
    now: datetime,
    client_factory: ClientFactory,
) -> str:
    """One attempt. Returns what happened: done-already, waiting, skipped, succeeded, failed."""
    from kiteconnect import exceptions as kex

    today = ist_date(now)
    if has_run_on(conn, JOB, today, ("succeeded", "skipped")):
        return "done-already"

    token = current_access_token(conn, now=now)
    if token is None:
        if now.astimezone(IST).time() >= FINAL_ATTEMPT:
            record_run(conn, JOB, "skipped", "no Kite session by 23:00 IST", at=now)
            raise_alert(
                conn,
                PRICE_RUN_SKIPPED,
                f"Price update for {today:%d-%b-%Y} skipped: Kite was not connected by 23:00 IST.",
            )
            return "skipped"
        raise_alert(
            conn,
            KITE_NOT_CONNECTED,
            "Connect Kite (http://localhost:8000/kite/login) so tonight's price update can run.",
        )
        return "waiting"

    run_id = start_run(conn, JOB, at=now)
    client = client_factory(settings, token)
    kite = settings.kite
    try:
        mapping = refresh_instruments(conn, client, as_of=today)
        limiter = RateLimiter(kite.historical_requests_per_second)
        result = ingest_daily_prices(
            conn,
            client,
            price_targets(conn, as_of=today),
            today=today,
            history_years=kite.history_years,
            max_days_per_request=kite.max_days_per_request,
            limiter=limiter,
        )
        index_rows, missing = ingest_index_prices(
            conn,
            client,
            kite.index_codes,
            as_of=today,
            today=today,
            history_years=kite.history_years,
            max_days_per_request=kite.max_days_per_request,
            limiter=limiter,
        )
    except kex.TokenException:
        finish_run(conn, run_id, "failed", "Kite rejected the session token")
        raise_alert(conn, KITE_NOT_CONNECTED, "Kite rejected the session. Log in again.")
        return "failed"
    except Exception as exc:
        finish_run(conn, run_id, "failed", f"{type(exc).__name__}: {exc}")
        raise
    detail = {
        "instruments": mapping.instruments,
        "mapped": mapping.mapped,
        "targets": result.targets,
        "requests": result.requests,
        "rows": result.rows,
        "invalid_candles": result.invalid_candles,
        "rebased": len(result.rebased),
        "failures": len(result.failures),
        "index_rows": index_rows,
        "missing_indices": missing,
    }
    finish_run(conn, run_id, "succeeded", json.dumps(detail))
    resolve_alert(conn, PRICE_RUN_SKIPPED)
    return "succeeded"
