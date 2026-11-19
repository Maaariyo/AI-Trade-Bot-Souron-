from services.worker.main import HEARTBEAT_SECONDS, build_scheduler


def test_scheduler_runs_heartbeat_in_ist() -> None:
    scheduler = build_scheduler()
    job = scheduler.get_job("heartbeat")
    assert job is not None
    assert str(scheduler.timezone) == "Asia/Kolkata"
    assert job.trigger.interval.total_seconds() == HEARTBEAT_SECONDS
