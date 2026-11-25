import pytest

from services.config import EffortConfig, Settings

AGENTS = {
    "risk_on",
    "capital_preserver",
    "deep_reasoner",
    "news_catalyst",
    "company_peers",
    "industry_macro",
    "management_governance",
    "verifier",
    "chair",
    "guidance_extractor",
}


def test_defaults_match_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("BUDGET__PER_DAY_USD", "BUDGET__PER_MONTH_USD", "MODE", "KILL_SWITCH"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.models.opus == "claude-opus-5-5"
    assert s.models.sonnet == "claude-sonnet-5-5"
    assert s.models.haiku == "claude-haiku-5-5"
    assert s.budget.per_day_usd == 25.0
    assert s.budget.per_month_usd == 300.0
    assert s.mode == "personal"
    assert s.kill_switch is False
    assert s.effort.deep_reasoner == "high"


def test_every_agent_has_an_effort_level() -> None:
    assert set(EffortConfig.model_fields) == AGENTS


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET__PER_DAY_USD", "10")
    monkeypatch.setenv("EFFORT__CHAIR", "medium")
    s = Settings(_env_file=None)
    assert s.budget.per_day_usd == 10.0
    assert s.effort.chair == "medium"


def test_secrets_are_not_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    s = Settings(_env_file=None)
    assert "sk-test-123" not in repr(s)
