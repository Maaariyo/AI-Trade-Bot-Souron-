"""APScheduler worker: heartbeat and the nightly price update. Full pipeline: Phase 6.

Run with: python -m services.worker.main
"""

import logging
from datetime import UTC, datetime

import psycopg
from apscheduler.schedulers.blocking import BlockingScheduler

from services.config import get_settings
from services.db import connect
from services.ingest.kite_auth import make_client
from services.worker.prices_job import SCHEDULE_HOURS_MINUTES, run_prices

TIMEZONE = "Asia/Kolkata"
HEARTBEAT_SECONDS = 60

log = logging.getLogger(__name__)


def record_heartbeat(url: str | None = None) -> None:
    """Write one succeeded 'heartbeat' row to job_runs."""
    with connect(url) as conn:
        conn.execute(
            "INSERT INTO job_runs (job_name, status, finished_at) "
            "VALUES ('heartbeat', 'succeeded', now())"
        )


def heartbeat() -> None:
    try:
        record_heartbeat()
    except psycopg.Error:
        log.exception("heartbeat failed: database unavailable")


def prices() -> None:
    try:
        with connect() as conn:
            conn.autocommit = True
            outcome = run_prices(
                conn,
                get_settings(),
                now=datetime.now(UTC),
                client_factory=lambda s, token: make_client(s, token),
            )
        log.info("price job: %s", outcome)
    except Exception:
        log.exception("price job crashed")


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=HEARTBEAT_SECONDS,
        id="heartbeat",
        max_instances=1,
        coalesce=True,
    )
    for hour, minute in SCHEDULE_HOURS_MINUTES:
        scheduler.add_job(
            prices,
            "cron",
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            id=f"prices-{hour:02d}{minute:02d}",
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    heartbeat()
    log.info("worker started; heartbeat every %ss", HEARTBEAT_SECONDS)
    build_scheduler().start()


if __name__ == "__main__":
    main()
