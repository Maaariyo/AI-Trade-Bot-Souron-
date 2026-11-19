from services.worker.main import HEARTBEAT_SECONDS, build_scheduler


def test_scheduler_runs_heartbeat_in_ist() -> None:
    scheduler = build_scheduler()
    job = scheduler.get_job("heartbeat")
    assert job is not None
    assert str(scheduler.timezone) == "Asia/Kolkata"
    assert job.trigger.interval.total_seconds() == HEARTBEAT_SECONDS


def test_price_job_scheduled_weekdays_from_1830_to_2300_ist() -> None:
    ids = sorted(j.id for j in build_scheduler().get_jobs() if j.id.startswith("prices-"))
    assert ids == [
        "prices-1830",
        "prices-1930",
        "prices-2030",
        "prices-2130",
        "prices-2230",
        "prices-2300",
    ]
