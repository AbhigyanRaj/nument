# Tests that settings load correctly from the environment and .env.example.

from datetime import date
from pathlib import Path

import pytest

from app.config import Settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

ENV_KEYS = [
    "LLM_PROVIDER",
    "LLM_MODEL",
    "GEMINI_API_KEY",
    "MOCK_LLM",
    "PLANNING_START",
    "SOLVER",
    "REQUIRE_AUTH",
    "COOKIE_SECURE",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_env_example_loads_exactly_as_written():
    s = Settings(_env_file=EXAMPLE)
    assert s.llm_provider == "gemini"
    assert s.llm_model == "gemini-3.8-flash"
    assert s.gemini_api_key.get_secret_value() == ""
    assert s.mock_llm is False
    assert s.planning_start is None  # blank value with an inline comment
    assert s.ship_offset_days == 4
    assert s.default_energy_price_per_kwh == pytest.approx(0.10)
    assert s.solver == "cpsat"
    assert s.require_auth is False
    assert s.cookie_secure is False
    assert s.analyze_max_concurrency == 2


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("PLANNING_START", "2026-10-12")
    monkeypatch.setenv("SOLVER", "greedy")
    s = Settings(_env_file=None)
    assert s.mock_llm is True
    assert s.planning_start == date(2026, 10, 12)
    assert s.solver == "greedy"


def test_api_keys_never_appear_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key-value")
    s = Settings(_env_file=None)
    assert "not-a-real-key-value" not in repr(s)
    assert s.gemini_api_key.get_secret_value() == "not-a-real-key-value"


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "made-up")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
