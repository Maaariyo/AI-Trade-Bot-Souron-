"""APScheduler worker. Phase 0 runs only a heartbeat; the nightly pipeline is Phase 6.

Run with: python -m services.worker.main
"""

import logging

import psycopg
from apscheduler.schedulers.blocking import BlockingScheduler

from services.db import connect

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
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    heartbeat()
    log.info("worker started; heartbeat every %ss", HEARTBEAT_SECONDS)
    build_scheduler().start()


if __name__ == "__main__":
    main()
