"""Environment-backed application settings.

Settings describe the agent service itself, never the system under test (target environments
live in their own allow-listed configuration). They are an immutable value object built once by
the composition root and passed down explicitly; no other module reads environment variables.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["development", "test", "ci", "staging", "production"]
LLMProviderName = Literal["mock"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["json", "console"]


class Settings(BaseSettings):
    """Validated runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=None,  # .env loading is opt-in via load_settings(env_file=...)
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = Field(default="autonomous-qa-agent", min_length=1, max_length=100)
    app_env: AppEnv = "development"
    llm_provider: LLMProviderName = "mock"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"
    artifacts_dir: Path = Path("artifacts")

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("app_env", "llm_provider", "log_format", mode="before")
    @classmethod
    def _normalise_lower(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Build settings from the process environment, optionally overlaid by an env file."""
    return Settings(_env_file=env_file)
