"""Tests for structured logging and correlation context."""

import json
import logging

from autonomous_qa_agent.logging_config import JsonLogFormatter, log_context


def test_json_formatter_includes_correlation_and_trace_ids() -> None:
    record = logging.LogRecord("qa.agent", logging.INFO, __file__, 1, "request done", (), None)
    with log_context("correlation-123", "trace-456"):
        payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "request done"
    assert payload["correlation_id"] == "correlation-123"
    assert payload["trace_id"] == "trace-456"
    assert payload["level"] == "INFO"


def test_json_formatter_includes_structured_error_fields() -> None:
    record = logging.LogRecord("qa.agent", logging.WARNING, __file__, 1, "failed", (), None)
    record.error_code = "provider_error"
    record.error_type = "ProviderError"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["error_code"] == "provider_error"
    assert payload["error_type"] == "ProviderError"


def test_json_formatter_defaults_identifiers_to_null() -> None:
    record = logging.LogRecord("qa.agent", logging.INFO, __file__, 1, "outside request", (), None)

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["correlation_id"] is None
    assert payload["trace_id"] is None


def test_log_context_restores_previous_values_after_nested_context() -> None:
    record = logging.LogRecord("qa.agent", logging.INFO, __file__, 1, "nested", (), None)
    with log_context("outer"):
        with log_context("inner", "trace"):
            nested = json.loads(JsonLogFormatter().format(record))
        restored = json.loads(JsonLogFormatter().format(record))

    assert nested["correlation_id"] == "inner"
    assert restored["correlation_id"] == "outer"
    assert restored["trace_id"] is None
