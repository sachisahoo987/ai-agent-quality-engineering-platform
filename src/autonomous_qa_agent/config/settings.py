"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="autonomous-qa-agent", min_length=1, max_length=100)
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    llm_provider: Literal["mock"] = "mock"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""
    return Settings()
