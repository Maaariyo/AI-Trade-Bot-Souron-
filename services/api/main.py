"""FastAPI application. Routers arrive per phase."""

from datetime import datetime
from typing import Literal

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel

from services.api.guidance import router as guidance_router
from services.api.kite import router as kite_router
from services.config import get_settings
from services.db import connect

app = FastAPI(title="NiveshCouncil API", version="0.1.0")
app.include_router(kite_router)
app.include_router(guidance_router)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "unavailable"]
    worker_last_heartbeat: datetime | None
    mode: Literal["personal", "publish"]
    kill_switch: bool


@app.get("/health")
def health() -> HealthResponse:
    settings = get_settings()
    db: Literal["ok", "unavailable"] = "ok"
    heartbeat: datetime | None = None
    try:
        with connect(connect_timeout=2) as conn:
            row = conn.execute(
                "SELECT max(started_at) FROM job_runs "
                "WHERE job_name = 'heartbeat' AND status = 'succeeded'"
            ).fetchone()
            heartbeat = row[0] if row else None
    except psycopg.Error:
        db = "unavailable"
    return HealthResponse(
        status="ok" if db == "ok" else "degraded",
        db=db,
        worker_last_heartbeat=heartbeat,
        mode=settings.mode,
        kill_switch=settings.kill_switch,
    )
