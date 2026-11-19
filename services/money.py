"""Money and time helpers shared by every service.

Money is integer paise (CLAUDE.md conventions). Conversions go through Decimal
so 2456.35 becomes 245635, never 245634.99999.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def to_paise(rupees: float | int | str | Decimal) -> int:
    """Rupees to integer paise, rounding half up."""
    value = Decimal(str(rupees)) * 100
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_rupees(paise: int) -> Decimal:
    return Decimal(paise) / 100


def ist_date(instant: datetime) -> date:
    """The IST calendar date of an aware datetime."""
    if instant.tzinfo is None:
        raise ValueError("expected a timezone-aware datetime")
    return instant.astimezone(IST).date()


def next_ist_time(after: datetime, at: time) -> datetime:
    """The first instant strictly after `after` whose IST wall-clock time is `at`."""
    local = after.astimezone(IST)
    candidate = datetime.combine(local.date(), at, tzinfo=IST)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=IST)
    return candidate
