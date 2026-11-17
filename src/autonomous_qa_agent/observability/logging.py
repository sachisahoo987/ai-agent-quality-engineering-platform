"""Structured logging on top of the standard library.

Built on stdlib ``logging`` (not a separate logging framework) so that records emitted by
third-party libraries such as LangGraph, httpx or the MCP SDK share one format and one pipeline.

Usage::

    configure_logging(settings.log_level, settings.log_format)    # once, in the composition root
    log = get_logger(__name__)
    with log_context(run_id=str(run_id), node="plan_execution"):
        log.info("plan created", extra={"tests": 3})

Every line carries the bound context plus any ``extra`` fields. Values stored under sensitive
keys (``password``, ``access_token``, ``api_key`` ...) are redacted recursively. Redaction works
on keys only; never interpolate secrets into the message text.
"""

import json
import logging
import re
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, TextIO

REDACTED = "***REDACTED***"

# A key is sensitive when one of its "_" or "-" separated segments is a sensitive word,
# so "access_token" is redacted while "prompt_tokens" is not.
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|authorization|"
    r"cookie|credentials?|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)

_EMPTY: Mapping[str, Any] = MappingProxyType({})
_context: ContextVar[Mapping[str, Any]] = ContextVar("log_context", default=_EMPTY)

# Attributes every LogRecord has; anything else on a record came from ``extra=``.
_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
}
_HANDLER_MARKER = "_autonomous_qa_agent_handler"


def _is_sensitive(key: object) -> bool:
    return isinstance(key, str) and _SENSITIVE_KEY.search(key) is not None


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with everything under a sensitive key masked."""
    if isinstance(value, Mapping):
        return {k: REDACTED if _is_sensitive(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    return value


def current_log_context() -> Mapping[str, Any]:
    """The fields currently bound by enclosing ``log_context`` blocks (read-only)."""
    return _context.get()


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Bind fields (run_id, node, scenario_id, ...) to every record emitted in this context.

    Nested contexts merge; inner values win; the outer context is restored on exit.
    Context variables propagate into asyncio tasks created inside the block.
    """
    token = _context.set(MappingProxyType({**_context.get(), **fields}))
    try:
        yield
    finally:
        _context.reset(token)


def _record_fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = dict(_context.get())
    fields.update(
        (k, v)
        for k, v in record.__dict__.items()
        if k not in _RECORD_ATTRS and not k.startswith("_")
    )
    return redact(fields)  # type: ignore[no-any-return]


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger, message, context and extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in _record_fields(record).items():
            payload.setdefault(key, value)  # never let an extra overwrite the core fields
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


class ConsoleLogFormatter(logging.Formatter):
    """Human-readable single line for local development: ``time LEVEL logger message k=v``."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, UTC).strftime("%H:%M:%S.%f")[:-3]
        fields = " ".join(f"{k}={v!r}" for k, v in _record_fields(record).items())
        line = f"{timestamp} {record.levelname:<8} {record.name} {record.getMessage()}"
        if fields:
            line = f"{line} {fields}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(
    level: str = "INFO",
    fmt: Literal["json", "console"] = "json",
    stream: TextIO | None = None,
) -> logging.Handler:
    """Install this package's handler on the root logger and return it.

    Idempotent: a handler installed by an earlier call is replaced; handlers installed by
    anyone else (pytest, an application server) are left untouched.
    """
    numeric_level = logging.getLevelNamesMapping().get(level.strip().upper())
    if numeric_level is None:
        raise ValueError(f"unsupported log level: {level!r}")
    if fmt not in ("json", "console"):
        raise ValueError(f"unsupported log format: {fmt!r}")

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonLogFormatter() if fmt == "json" else ConsoleLogFormatter())
    setattr(handler, _HANDLER_MARKER, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(numeric_level)
    return handler


def get_logger(name: str) -> logging.Logger:
    """Return a standard logger; kept as the single import point for application code."""
    return logging.getLogger(name)
