"""Centralised error handling: every entry point (CLI now, API later) turns exceptions into an
``ErrorResponse`` here, so callers get the same shape and never see internal detail.

- ``QAAgentError`` subclasses are expected failures: the caller gets their ``code``,
  ``public_message`` and public-safe ``details``; the internal message is logged.
- Anything else is a bug: the caller gets a generic ``internal_error``; the traceback is logged.

Both carry the current ``trace_id`` so a reported error can be matched to its log lines.
"""

from autonomous_qa_agent.models.agent import ErrorResponse
from autonomous_qa_agent.models.errors import InvalidRequestError, QAAgentError
from autonomous_qa_agent.observability.logging import current_trace_id, get_logger

INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "An unexpected error occurred."

EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_INVALID_REQUEST = 2

_log = get_logger(__name__)


def to_error_response(exc: Exception) -> ErrorResponse:
    """Log ``exc`` and return what may be shown to the caller."""
    trace_id = current_trace_id()
    if isinstance(exc, QAAgentError):
        _log.warning("request failed", extra={"error_code": exc.code, "error_message": str(exc)})
        return ErrorResponse(
            code=exc.code, message=exc.public_message, details=exc.details, trace_id=trace_id
        )
    _log.error("unexpected error", exc_info=exc, extra={"error_code": INTERNAL_ERROR_CODE})
    return ErrorResponse(
        code=INTERNAL_ERROR_CODE, message=INTERNAL_ERROR_MESSAGE, trace_id=trace_id
    )


def exit_code_for(error: ErrorResponse) -> int:
    """Process exit code for a CLI failure: 2 for bad input, 1 for everything else."""
    return EXIT_INVALID_REQUEST if error.code == InvalidRequestError.code else EXIT_INTERNAL_ERROR
