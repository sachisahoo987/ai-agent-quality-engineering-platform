"""Structured JSON logging and request correlation context."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


class JsonLogFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a record with timestamps and active request identifiers."""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id.get(),
            "trace_id": _trace_id.get(),
        }
        for field in ("error_code", "error_type"):
            if value := getattr(record, field, None):
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@contextmanager
def log_context(correlation_id: str, trace_id: str | None = None) -> Iterator[None]:
    """Set correlation identifiers for logs emitted in the current context."""
    correlation_token = _correlation_id.set(correlation_id)
    trace_token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(trace_token)
        _correlation_id.reset(correlation_token)


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON to standard output."""
    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        raise ValueError(f"unsupported log level: {level}")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(resolved_level)
