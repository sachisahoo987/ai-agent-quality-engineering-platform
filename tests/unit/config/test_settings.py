from pathlib import Path

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.config import Settings, load_settings

ENV_VARS = ("APP_NAME", "APP_ENV", "LLM_PROVIDER", "LOG_LEVEL", "LOG_FORMAT", "ARTIFACTS_DIR")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    settings = load_settings()
    assert settings.app_env == "development"
    assert settings.llm_provider == "mock"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.artifacts_dir == Path("artifacts")


def test_values_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    monkeypatch.setenv("APP_ENV", "CI")
    monkeypatch.setenv("LOG_FORMAT", "Console")
    monkeypatch.setenv("LLM_PROVIDER", "MOCK")
    settings = load_settings()
    assert (settings.log_level, settings.app_env, settings.log_format) == ("DEBUG", "ci", "console")
    assert settings.llm_provider == "mock"


@pytest.mark.parametrize(
    ("name", "value"),
    [("LLM_PROVIDER", "openai"), ("LOG_LEVEL", "verbose"), ("APP_ENV", "qa"), ("APP_NAME", "")],
)
def test_invalid_values_fail_fast(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        load_settings()


def test_env_file_is_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load_settings().log_level == "INFO"  # .env in cwd is ignored by default
    assert load_settings(env_file).log_level == "WARNING"


def test_process_env_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    assert load_settings(env_file).log_level == "ERROR"


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.log_level = "DEBUG"  # type: ignore[misc]
