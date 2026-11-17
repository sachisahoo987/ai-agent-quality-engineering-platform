"""Tests for environment-backed settings."""

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.config import Settings, get_settings


def test_settings_load_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "qa-test-runner")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    settings = Settings()

    assert settings.app_name == "qa-test-runner"
    assert settings.app_env == "test"
    assert settings.log_level == "DEBUG"
    assert settings.llm_provider == "mock"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("APP_ENV", "unknown"),
        ("LOG_LEVEL", "TRACE"),
        ("LLM_PROVIDER", "remote"),
    ],
)
def test_settings_reject_unsupported_values(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
) -> None:
    monkeypatch.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings()


def test_settings_are_immutable() -> None:
    settings = Settings()

    with pytest.raises(ValidationError):
        settings.app_env = "test"


def test_get_settings_returns_cached_instance() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()
