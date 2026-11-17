import asyncio
import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from autonomous_qa_agent.observability import (
    REDACTED,
    configure_logging,
    current_log_context,
    get_logger,
    log_context,
    redact,
)


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    root = logging.getLogger()
    previous_level = root.level
    handler = configure_logging("DEBUG", "json", stream=buffer)
    yield buffer
    root.removeHandler(handler)
    root.setLevel(previous_level)


def _lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize(
    "key",
    [
        "password",
        "MYSQL_PASSWORD",
        "access_token",
        "api_key",
        "x-api-key",
        "Authorization",
        "cookie",
        "client_secret",
        "credentials",
        "private_key",
    ],
)
def test_sensitive_keys_are_redacted(key: str) -> None:
    assert redact({key: "s3cr3t"}) == {key: REDACTED}


@pytest.mark.parametrize("key", ["prompt_tokens", "tokens", "tokenizer", "user", "step_id"])
def test_ordinary_keys_are_kept(key: str) -> None:
    # Only a whole "_"/"-" separated segment counts: LLM usage fields must stay visible.
    assert redact({key: "v"}) == {key: "v"}


def test_redaction_is_recursive_and_non_mutating() -> None:
    original = {"headers": [{"Authorization": "Bearer x"}, ("ok", {"password": "p"})], "n": 1}
    redacted = redact(original)
    assert redacted == {
        "headers": [{"Authorization": REDACTED}, ("ok", {"password": REDACTED})],
        "n": 1,
    }
    assert original["headers"][0]["Authorization"] == "Bearer x"


# ------------------------------------------------------------------ JSON output
def test_json_line_has_core_fields_context_and_extras(stream: io.StringIO) -> None:
    log = get_logger("qa.test")
    with log_context(run_id="r-1", node="plan"):
        log.info("plan created", extra={"tests": 3, "api_key": "k"})
    (line,) = _lines(stream)
    assert line["level"] == "INFO"
    assert line["logger"] == "qa.test"
    assert line["message"] == "plan created"
    assert line["timestamp"].endswith("+00:00")
    assert (line["run_id"], line["node"], line["tests"]) == ("r-1", "plan", 3)
    assert line["api_key"] == REDACTED


def test_extras_cannot_overwrite_core_fields(stream: io.StringIO) -> None:
    with log_context(level="FAKE"):
        get_logger("qa").warning("real")
    (line,) = _lines(stream)
    assert line["level"] == "WARNING"


def test_exception_and_non_json_values(stream: io.StringIO) -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("qa").exception("failed", extra={"obj": object()})
    (line,) = _lines(stream)
    assert "RuntimeError: boom" in line["exception"]
    assert line["obj"].startswith("<object object")


def test_stack_info_is_included(stream: io.StringIO) -> None:
    get_logger("qa").info("with stack", stack_info=True)
    assert "Stack (most recent call last)" in _lines(stream)[0]["stack"]


def test_level_filtering(stream: io.StringIO) -> None:
    logging.getLogger().setLevel(logging.WARNING)
    get_logger("qa").info("hidden")
    get_logger("qa").warning("shown")
    assert [line["message"] for line in _lines(stream)] == ["shown"]


# ------------------------------------------------------------------ context
def test_nested_context_merges_and_restores() -> None:
    with log_context(run_id="r-1", node="a"):
        with log_context(node="b", step_id="s-1"):
            assert current_log_context() == {"run_id": "r-1", "node": "b", "step_id": "s-1"}
        assert current_log_context() == {"run_id": "r-1", "node": "a"}
    assert current_log_context() == {}


async def test_context_propagates_to_asyncio_tasks() -> None:
    async def read() -> dict[str, Any]:
        return dict(current_log_context())

    with log_context(run_id="r-9"):
        assert await asyncio.create_task(read()) == {"run_id": "r-9"}


def test_context_is_restored_after_exception() -> None:
    with pytest.raises(ValueError, match="x"), log_context(run_id="r"):
        raise ValueError("x")
    assert current_log_context() == {}


# ------------------------------------------------------------------ configuration
def test_console_format(stream: io.StringIO) -> None:
    buffer = io.StringIO()
    handler = configure_logging("INFO", "console", stream=buffer)
    try:
        with log_context(run_id="r-1"):
            get_logger("qa").info("hello", extra={"password": "p"})
        try:
            raise KeyError("k")
        except KeyError:
            get_logger("qa").exception("bad")
    finally:
        logging.getLogger().removeHandler(handler)
    out = buffer.getvalue()
    assert "INFO     qa hello run_id='r-1' password='***REDACTED***'" in out
    assert "KeyError: 'k'" in out
    assert stream.getvalue() == ""  # the earlier handler was replaced, not duplicated


def test_configure_is_idempotent_and_keeps_foreign_handlers() -> None:
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    first = configure_logging("INFO")
    second = configure_logging("INFO")
    try:
        assert first not in root.handlers
        assert second in root.handlers
        assert foreign in root.handlers
    finally:
        root.removeHandler(second)
        root.removeHandler(foreign)


@pytest.mark.parametrize(("level", "fmt"), [("LOUD", "json"), ("INFO", "xml")])
def test_configure_rejects_invalid_options(level: str, fmt: Any) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        configure_logging(level, fmt)
