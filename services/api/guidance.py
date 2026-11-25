"""Guidance review routes (Phase 1b). The review screen at /guidance calls these."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.db import connect
from services.mgmt_guidance import review
from services.mgmt_guidance.extract import Metric, StatedUnit

router = APIRouter(prefix="/guidance")


def utcnow() -> datetime:
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(utcnow)]


class GuidanceOut(BaseModel):
    id: int
    isin: str
    document_id: int
    method: str
    stated_on: date
    metric: str
    metric_detail: str | None
    target_period: str
    target_low_stated: Decimal
    target_high_stated: Decimal
    unit_stated: str
    quote: str
    page_no: int | None
    status: str
    flag: str | None
    review_note: str | None


class StatsOut(BaseModel):
    by_status: dict[str, int]
    llm_reviewed: int
    llm_approved: int
    verified_reviewed: int
    verified_approved: int
    agreement: float | None


class ReviewIn(BaseModel):
    note: str | None = None


class ManualIn(BaseModel):
    document_id: int
    metric: Metric
    metric_detail: str | None = None
    target_period: str
    target_low: Decimal
    target_high: Decimal
    unit: StatedUnit
    quote: str
    note: str | None = None


def _out(v: review.GuidanceView) -> GuidanceOut:
    return GuidanceOut(**v.__dict__)


@router.get("")
def list_rows(status: str | None = None, isin: str | None = None) -> list[GuidanceOut]:
    with connect() as conn:
        return [_out(v) for v in review.list_guidance(conn, status=status, isin=isin)]


@router.get("/stats")
def stats() -> StatsOut:
    with connect() as conn:
        s = review.review_stats(conn)
    return StatsOut(**s.__dict__, agreement=s.agreement)


def _act(action: Callable[..., None], guidance_id: int, body: ReviewIn, now: datetime) -> None:
    try:
        with connect() as conn:
            action(conn, guidance_id, note=body.note, now=now)
    except review.ReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{guidance_id}/approve", status_code=204)
def approve(guidance_id: int, body: ReviewIn, now: Now) -> None:
    _act(review.approve, guidance_id, body, now)


@router.post("/{guidance_id}/reject", status_code=204)
def reject(guidance_id: int, body: ReviewIn, now: Now) -> None:
    _act(review.reject, guidance_id, body, now)


@router.post("/manual", status_code=201)
def add_manual(body: ManualIn, now: Now) -> dict[str, int]:
    try:
        with connect() as conn:
            gid = review.add_manual(conn, now=now, **body.model_dump())
    except review.ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": gid}
