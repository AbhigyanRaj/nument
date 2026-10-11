"""Application settings, read from the environment and an optional .env file."""

import os
from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: a blank line such as "PLANNING_START=" means "use the default",
    # not "parse an empty string". ENV_FILE lets tests opt out of the developer's .env.
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"), extra="ignore", env_ignore_empty=True
    )

    # LLM
    llm_provider: Literal["gemini", "openai", "anthropic", "ollama"] = "gemini"
    llm_model: str = "gemini-3.8-flash"
    gemini_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    ollama_base_url: str = "http://host.docker.internal:11434"
    mock_llm: bool = False

    # Data and planning
    db_url: str = "sqlite:///data/allocation.db"
    planning_start: date | None = None
    ship_offset_days: int = 4
    default_energy_price_per_kwh: float = 0.10
    solver: Literal["cpsat", "greedy"] = "cpsat"
    solver_time_limit_s: float = 10
    api_url: str = "http://localhost:8000"
    autoload_sample: bool = True

    # Accounts and security
    require_auth: bool = False
    api_key: SecretStr = SecretStr("")
    allow_signup: bool = True
    demo_email: str = ""
    demo_password: SecretStr = SecretStr("")
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    max_upload_mb: float = 5
    rate_limit_login_per_minute: int = 10
    analyze_max_concurrency: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
