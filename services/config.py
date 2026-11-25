"""Settings loaded from the environment (.env in development).

Model IDs, effort levels and budget caps live here, never in agent code
(CLAUDE.md, "Claude API rules"). Values are the SPEC v2 defaults.
"""

from datetime import time
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class ModelConfig(BaseModel):
    """Model IDs per tier. SPEC section 6, "Standard" setup."""

    opus: str = "claude-opus-5-5"
    sonnet: str = "claude-sonnet-5-5"
    haiku: str = "claude-haiku-5-5"


class EffortConfig(BaseModel):
    """Starting effort per agent. SPEC section 6; Phase 4 tunes these."""

    risk_on: Effort = "low"
    capital_preserver: Effort = "low"
    deep_reasoner: Effort = "high"
    news_catalyst: Effort = "medium"
    company_peers: Effort = "medium"
    industry_macro: Effort = "medium"
    management_governance: Effort = "medium"
    verifier: Effort = "low"
    chair: Effort = "low"
    guidance_extractor: Effort = "low"


class BudgetConfig(BaseModel):
    """Hard spend caps in US dollars (open decision D4)."""

    per_day_usd: float = Field(default=25.0, gt=0)
    per_month_usd: float = Field(default=300.0, gt=0)


class ModelPrice(BaseModel):
    """US dollars per million tokens, first-party API, standard (not batch) rates."""

    input: float
    output: float
    cache_read: float
    long_context_threshold: int | None = None  # prompts above this use the long rates
    long_input: float | None = None
    long_output: float | None = None


class PricingConfig(BaseModel):
    """Claude prices as of Nov 2026 (SPEC section 12). Batches cost 50% of these."""

    batch_discount: float = 0.5
    cache_write_multiplier: float = 1.25
    models: dict[str, ModelPrice] = {
        "claude-opus-5-5": ModelPrice(input=4.0, output=20.0, cache_read=0.20),
        "claude-sonnet-5-5": ModelPrice(input=2.0, output=10.0, cache_read=0.10),
        "claude-haiku-5-5": ModelPrice(
            input=0.10,
            output=0.50,
            cache_read=0.01,
            long_context_threshold=100_000,
            long_input=0.50,
            long_output=2.50,
        ),
    }


class KiteConfig(BaseModel):
    """Kite Connect limits. Values to confirm against Zerodha's docs (docs/VENDORS.md)."""

    token_expiry_ist: time = time(6, 0)
    historical_requests_per_second: float = Field(default=3.0, gt=0)
    max_days_per_request: int = Field(default=1900, gt=0)
    history_years: int = Field(default=5, gt=0)
    # Kite trading symbols for indices; any not found are reported by `make ingest`.
    index_codes: list[str] = [
        "NIFTY 50",
        "NIFTY 500",
        "NIFTY BANK",
        "NIFTY IT",
        "NIFTY AUTO",
        "NIFTY FMCG",
        "NIFTY PHARMA",
        "NIFTY METAL",
        "NIFTY REALTY",
        "NIFTY ENERGY",
        "NIFTY FIN SERVICE",
        "NIFTY MEDIA",
        "NIFTY PSU BANK",
        "NIFTY PVT BANK",
    ]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    database_url: str = "postgresql://nivesh:nivesh@localhost:5432/nivesh"
    anthropic_api_key: SecretStr | None = None
    kite_api_key: SecretStr | None = None
    kite_api_secret: SecretStr | None = None
    mode: Literal["personal", "publish"] = "personal"
    kill_switch: bool = False

    models: ModelConfig = ModelConfig()
    effort: EffortConfig = EffortConfig()
    budget: BudgetConfig = BudgetConfig()
    kite: KiteConfig = KiteConfig()
    pricing: PricingConfig = PricingConfig()
    news_feeds: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
