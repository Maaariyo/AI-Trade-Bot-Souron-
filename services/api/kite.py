"""Kite login routes and alerts. The access token never leaves the server.

Set the redirect URL of your Kite Connect app to http://localhost:8000/kite/callback.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from services.alerts import open_alerts
from services.config import Settings, get_settings
from services.db import connect
from services.ingest.kite_auth import (
    KiteClient,
    KiteNotConfigured,
    complete_login,
    make_client,
    session_status,
)
from services.money import IST

router = APIRouter()


def kite_client_factory() -> Callable[[Settings], KiteClient]:
    return make_client


def utcnow() -> datetime:
    return datetime.now(UTC)


ClientFactory = Annotated[Callable[[Settings], KiteClient], Depends(kite_client_factory)]
Now = Annotated[datetime, Depends(utcnow)]


class KiteStatus(BaseModel):
    connected: bool
    expires_at: datetime | None


class AlertOut(BaseModel):
    kind: str
    message: str
    created_at: datetime


@router.get("/kite/status")
def kite_status(now: Now) -> KiteStatus:
    with connect() as conn:
        status = session_status(conn, now=now)
    return KiteStatus(connected=status.connected, expires_at=status.expires_at)


@router.get("/kite/login")
def kite_login(factory: ClientFactory) -> RedirectResponse:
    try:
        client = factory(get_settings())
    except KiteNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(client.login_url(), status_code=307)


@router.get("/kite/callback", response_class=HTMLResponse)
def kite_callback(
    factory: ClientFactory,
    now: Now,
    request_token: str | None = None,
    status: str | None = None,
) -> HTMLResponse:
    if status != "success" or not request_token:
        raise HTTPException(status_code=400, detail="Kite login did not succeed")
    settings = get_settings()
    try:
        client = factory(settings)
        with connect() as conn:
            expires = complete_login(conn, client, settings, request_token, now=now)
    except KiteNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    until = escape(expires.astimezone(IST).strftime("%d-%b-%Y %H:%M IST"))
    return HTMLResponse(
        f"<!doctype html><title>Kite connected</title>"
        f"<p>Kite connected until {until}. You can close this tab.</p>"
    )


@router.get("/alerts")
def alerts() -> list[AlertOut]:
    with connect() as conn:
        return [
            AlertOut(kind=a.kind, message=a.message, created_at=a.created_at)
            for a in open_alerts(conn)
        ]
