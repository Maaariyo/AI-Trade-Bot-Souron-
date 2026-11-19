"""Dividends, splits and bonuses, and the total-return maths that needs them.

Until a vendor is chosen (D1), actions load from a CSV in this project's own
layout, which any vendor export can be converted to:

    isin,action_type,ex_date,cash_per_share,shares_before,shares_after,record_date,
    available_from,description

`cash_per_share` is in rupees. `available_from` is when the action was announced
(ISO 8601 with a time zone); it keeps backtests point in time.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import psycopg
from psycopg.rows import TupleRow

from services.ingest.csvfiles import parse_date, read_rows
from services.money import to_paise

ActionType = Literal["DIVIDEND", "SPLIT", "BONUS", "RIGHTS", "OTHER"]


@dataclass(frozen=True)
class CorporateAction:
    isin: str
    action_type: ActionType
    ex_date: date
    available_from: datetime
    cash_paise_per_share: int | None = None
    shares_before: int | None = None
    shares_after: int | None = None
    record_date: date | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.available_from.tzinfo is None:
            raise ValueError(f"{self.isin} {self.ex_date}: available_from needs a time zone")
        if self.action_type == "DIVIDEND" and self.cash_paise_per_share is None:
            raise ValueError(f"{self.isin} {self.ex_date}: a dividend needs cash_per_share")
        if self.action_type in ("SPLIT", "BONUS") and not (
            self.shares_before and self.shares_after
        ):
            raise ValueError(f"{self.isin} {self.ex_date}: {self.action_type} needs a ratio")

    @property
    def share_factor(self) -> Decimal:
        """Shares held after the ex-date per share held before it."""
        if self.action_type in ("SPLIT", "BONUS") and self.shares_before and self.shares_after:
            return Decimal(self.shares_after) / Decimal(self.shares_before)
        return Decimal(1)


_ALIASES = {
    "isin": ("ISIN",),
    "action_type": ("ACTIONTYPE", "TYPE"),
    "ex_date": ("EXDATE",),
    "cash": ("CASHPERSHARE", "DIVIDENDPERSHARE", "AMOUNT"),
    "before": ("SHARESBEFORE",),
    "after": ("SHARESAFTER",),
    "record_date": ("RECORDDATE",),
    "available_from": ("AVAILABLEFROM", "ANNOUNCEDAT"),
    "description": ("DESCRIPTION", "PURPOSE"),
}


def parse_actions_csv(source: Path | str) -> list[CorporateAction]:
    rows = read_rows(source, _ALIASES, {"isin", "action_type", "ex_date", "available_from"})
    out: list[CorporateAction] = []
    for r in rows:
        ex = parse_date(r["ex_date"])
        if ex is None:
            raise ValueError(f"{r['isin']}: missing ex_date")
        out.append(
            CorporateAction(
                isin=r["isin"].upper(),
                action_type=r["action_type"].upper(),  # type: ignore[arg-type]
                ex_date=ex,
                available_from=datetime.fromisoformat(r["available_from"]),
                cash_paise_per_share=to_paise(r["cash"]) if r.get("cash") else None,
                shares_before=int(r["before"]) if r.get("before") else None,
                shares_after=int(r["after"]) if r.get("after") else None,
                record_date=parse_date(r.get("record_date", "")),
                description=r.get("description") or None,
            )
        )
    return out


def upsert_actions(
    conn: psycopg.Connection[TupleRow], actions: Iterable[CorporateAction], *, source: str
) -> int:
    params = [
        (
            a.isin,
            a.action_type,
            a.ex_date,
            a.record_date,
            a.cash_paise_per_share,
            a.shares_before,
            a.shares_after,
            a.description,
            source,
            a.available_from,
        )
        for a in actions
    ]
    if not params:
        return 0
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO corporate_actions (isin, action_type, ex_date, record_date,
                cash_paise_per_share, shares_before, shares_after, description, source,
                available_from)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (isin, action_type, ex_date, source) DO UPDATE SET
                record_date = EXCLUDED.record_date,
                cash_paise_per_share = EXCLUDED.cash_paise_per_share,
                shares_before = EXCLUDED.shares_before,
                shares_after = EXCLUDED.shares_after,
                description = EXCLUDED.description,
                available_from = EXCLUDED.available_from,
                ingested_at = now()
            """,
            params,
        )
    return len(params)


# --- Total returns -----------------------------------------------------------------


def total_return_index(
    closes: Sequence[tuple[date, int]],
    actions: Iterable[CorporateAction],
    *,
    prices_split_adjusted: bool,
    base: Decimal = Decimal(100),
) -> list[tuple[date, Decimal]]:
    """A total-return index from daily closes (paise) and corporate actions.

    Holding one share at the previous close, the day's return on an ex-date is
    (factor x close + dividend) / previous close, where factor is the split or
    bonus share multiplier. A dividend on the same day as a split is per
    pre-split share.

    If the price series is already split-adjusted, factor is 1 and each
    dividend is divided by the product of the factors of later splits, so it
    is in the same units as the adjusted prices.
    """
    acts = sorted(actions, key=lambda a: a.ex_date)
    splits = [a for a in acts if a.share_factor != 1]
    by_day_factor: dict[date, Decimal] = {}
    by_day_cash: dict[date, Decimal] = {}
    for a in acts:
        if a.share_factor != 1:
            by_day_factor[a.ex_date] = by_day_factor.get(a.ex_date, Decimal(1)) * a.share_factor
        if a.action_type == "DIVIDEND" and a.cash_paise_per_share:
            cash = Decimal(a.cash_paise_per_share)
            if prices_split_adjusted:
                for s in splits:
                    if s.ex_date > a.ex_date:
                        cash /= s.share_factor
                    elif s.ex_date == a.ex_date:
                        cash /= s.share_factor  # pre-split cash on a post-split price
            by_day_cash[a.ex_date] = by_day_cash.get(a.ex_date, Decimal(0)) + cash

    out: list[tuple[date, Decimal]] = []
    level = base
    prev: int | None = None
    for day, close in closes:
        if prev is not None:
            factor = Decimal(1) if prices_split_adjusted else by_day_factor.get(day, Decimal(1))
            level *= (factor * Decimal(close) + by_day_cash.get(day, Decimal(0))) / Decimal(prev)
        out.append((day, level))
        prev = close
    return out
