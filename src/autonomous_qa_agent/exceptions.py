"""Typed application exceptions and centralized response translation."""

from __future__ import annotations

import logging
from uuid import UUID

from autonomous_qa_agent.logging_config import log_context
from autonomous_qa_agent.models import AgentResponse, AgentStatus

logger = logging.getLogger(__name__)


class AgentError(Exception):
    """Base class for expected, safe-to-report agent errors."""

    code = "agent_error"
    public_message = "The agent could not complete the request."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)


class InvalidRequestError(AgentError):
    """Raised when an agent request cannot be processed."""

    code = "invalid_request"
    public_message = "The request is invalid."


class ProviderError(AgentError):
    """Raised when the configured LLM provider fails."""

    code = "provider_error"
    public_message = "The language model provider failed."


class ConfigurationError(AgentError):
    """Raised when runtime configuration is invalid or unsupported."""

    code = "configuration_error"
    public_message = "The agent configuration is invalid."


def error_to_response(
    error: Exception,
    *,
    request_id: UUID,
    correlation_id: UUID,
) -> AgentResponse:
    """Log an error and translate it into a safe, structured agent response."""
    with log_context(str(correlation_id)):
        if isinstance(error, AgentError):
            logger.warning(
                "Agent request failed",
                extra={"error_code": error.code, "error_type": type(error).__name__},
            )
            error_code = error.code
            message = error.public_message
        else:
            logger.error(
                "Unexpected agent failure",
                extra={"error_type": type(error).__name__},
                exc_info=(type(error), error, error.__traceback__),
            )
            error_code = "internal_error"
            message = "An unexpected error occurred."
    return AgentResponse(
        request_id=request_id,
        correlation_id=correlation_id,
        status=AgentStatus.FAILED,
        error_code=error_code,
        error_message=message,
    )
