"""Token costs, the usage ledger, and the budget check (CLAUDE.md rule 7).

Call `check_budget` before every LLM request, with a worst-case estimate.
It refuses when the kill switch is on, or when today's or this month's
spend (IST calendar) plus the estimate would pass the caps.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

import psycopg
from psycopg.rows import TupleRow

from services.config import Settings
from services.money import IST

MILLION = Decimal(1_000_000)


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


def cost_usd(settings: Settings, model: str, usage: Usage, *, batch: bool) -> Decimal:
    pricing = settings.pricing
    if model not in pricing.models:
        raise KeyError(f"no price configured for {model}; add it to PricingConfig")
    p = pricing.models[model]
    long_ctx = (
        p.long_context_threshold is not None and usage.prompt_tokens > p.long_context_threshold
    )
    in_rate = Decimal(str(p.long_input if long_ctx and p.long_input else p.input))
    out_rate = Decimal(str(p.long_output if long_ctx and p.long_output else p.output))
    total = (
        Decimal(usage.input_tokens) * in_rate
        + Decimal(usage.cache_write_tokens) * in_rate * Decimal(str(pricing.cache_write_multiplier))
        + Decimal(usage.cache_read_tokens) * Decimal(str(p.cache_read))
        + Decimal(usage.output_tokens) * out_rate
    ) / MILLION
    if batch:
        total *= Decimal(str(pricing.batch_discount))
    return total.quantize(Decimal("0.000001"))


def _ist_start(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=IST)


def spend_since(conn: psycopg.Connection[TupleRow], since: datetime) -> Decimal:
    row = conn.execute(
        "SELECT coalesce(sum(cost_usd), 0) FROM llm_usage WHERE at >= %s", (since,)
    ).fetchone()
    return Decimal(row[0]) if row else Decimal(0)


def check_budget(
    conn: psycopg.Connection[TupleRow], settings: Settings, estimate_usd: Decimal, *, now: datetime
) -> None:
    if settings.kill_switch:
        raise BudgetExceeded("kill switch is on; no LLM calls")
    today = now.astimezone(IST).date()
    day_spend = spend_since(conn, _ist_start(today))
    month_spend = spend_since(conn, _ist_start(today.replace(day=1)))
    day_cap = Decimal(str(settings.budget.per_day_usd))
    month_cap = Decimal(str(settings.budget.per_month_usd))
    if day_spend + estimate_usd > day_cap:
        raise BudgetExceeded(
            f"daily cap ${day_cap}: spent ${day_spend:.4f}, this call could add ${estimate_usd:.4f}"
        )
    if month_spend + estimate_usd > month_cap:
        raise BudgetExceeded(
            f"monthly cap ${month_cap}: spent ${month_spend:.4f}, "
            f"this call could add ${estimate_usd:.4f}"
        )


def record_usage(
    conn: psycopg.Connection[TupleRow],
    settings: Settings,
    *,
    purpose: str,
    request_ref: str,
    model_requested: str,
    model_served: str | None,
    usage: Usage,
    batch: bool,
    at: datetime,
) -> Decimal:
    cost = cost_usd(settings, model_served or model_requested, usage, batch=batch)
    conn.execute(
        """
        INSERT INTO llm_usage (at, purpose, request_ref, model_requested, model_served, batch,
            input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            at,
            purpose,
            request_ref,
            model_requested,
            model_served,
            batch,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            cost,
        ),
    )
    return cost
