"""Application service and LLM provider dependency injection."""

from __future__ import annotations

import logging
from uuid import uuid4

from pydantic import ValidationError

from autonomous_qa_agent.config import Settings
from autonomous_qa_agent.exceptions import (
    AgentError,
    ConfigurationError,
    InvalidRequestError,
    ProviderError,
    error_to_response,
)
from autonomous_qa_agent.llm import LLMProvider, MockLLMProvider
from autonomous_qa_agent.logging_config import log_context
from autonomous_qa_agent.models import AgentRequest, AgentResponse, AgentStatus

logger = logging.getLogger(__name__)


class AgentService:
    """Coordinate validated requests with an injected provider."""

    def __init__(self, provider: LLMProvider) -> None:
        """Create a service with an explicit provider dependency."""
        self._provider = provider

    def handle(
        self,
        task: str,
        *,
        context: dict[str, object] | None = None,
        trace_id: str | None = None,
    ) -> AgentResponse:
        """Process a task and return a structured success or failure response."""
        request_id = uuid4()
        correlation_id = uuid4()
        with log_context(str(correlation_id), trace_id):
            try:
                request = AgentRequest(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    task=task,
                    context=context or {},
                )
            except ValidationError:
                return error_to_response(
                    InvalidRequestError(),
                    request_id=request_id,
                    correlation_id=correlation_id,
                )

            try:
                output = self._provider.generate(request)
                if not isinstance(output, str) or not output.strip():
                    raise ProviderError("Provider returned an empty or non-text response.")
            except AgentError as error:
                return error_to_response(
                    error,
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
            except Exception as error:
                return error_to_response(
                    error,
                    request_id=request_id,
                    correlation_id=correlation_id,
                )

            logger.info("Agent request completed")
            return AgentResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                status=AgentStatus.COMPLETED,
                output=output,
            )


def create_agent_service(
    settings: Settings,
    provider: LLMProvider | None = None,
) -> AgentService:
    """Build the service from runtime settings and an optional injected provider."""
    if provider is not None:
        return AgentService(provider=provider)
    if settings.llm_provider == "mock":
        return AgentService(provider=MockLLMProvider())
    raise ConfigurationError("No provider is configured for the selected LLM backend.")
