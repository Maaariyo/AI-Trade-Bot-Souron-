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


def test_screen_runs_after_the_last_price_attempt() -> None:
    job = build_scheduler().get_job("screen-2330")
    assert job is not None
    assert "hour='23'" in str(job.trigger) and "minute='30'" in str(job.trigger)
