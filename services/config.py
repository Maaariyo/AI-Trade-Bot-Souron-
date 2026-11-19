"""Settings loaded from the environment (.env in development).

Model IDs, effort levels and budget caps live here, never in agent code
(CLAUDE.md, "Claude API rules"). Values are the SPEC v2 defaults.
"""

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


class BudgetConfig(BaseModel):
    """Hard spend caps in US dollars (open decision D4)."""

    per_day_usd: float = Field(default=25.0, gt=0)
    per_month_usd: float = Field(default=300.0, gt=0)


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
