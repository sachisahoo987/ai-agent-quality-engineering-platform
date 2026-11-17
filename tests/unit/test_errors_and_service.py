"""Tests for error translation and service dependency injection."""

from uuid import uuid4

import pytest

from autonomous_qa_agent.config import Settings
from autonomous_qa_agent.exceptions import (
    AgentError,
    ConfigurationError,
    InvalidRequestError,
    ProviderError,
    error_to_response,
)
from autonomous_qa_agent.llm import MockLLMProvider
from autonomous_qa_agent.models import AgentRequest, AgentStatus
from autonomous_qa_agent.services import AgentService, create_agent_service


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (InvalidRequestError("sensitive input detail"), "invalid_request"),
        (ProviderError("upstream implementation detail"), "provider_error"),
        (ConfigurationError(), "configuration_error"),
        (AgentError(), "agent_error"),
    ],
)
def test_known_errors_map_to_safe_responses(error: AgentError, expected_code: str) -> None:
    response = error_to_response(error, request_id=uuid4(), correlation_id=uuid4())

    assert response.status == AgentStatus.FAILED
    assert response.error_code == expected_code
    assert "detail" not in (response.error_message or "")


def test_unexpected_error_maps_to_generic_response_without_leaking_details(caplog) -> None:
    response = error_to_response(
        RuntimeError("secret implementation detail"),
        request_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert response.error_code == "internal_error"
    assert response.error_message == "An unexpected error occurred."
    assert "secret implementation detail" not in response.error_message
    assert "Unexpected agent failure" in caplog.text


def test_agent_service_injects_provider_and_returns_success() -> None:
    service = AgentService(provider=MockLLMProvider())

    response = service.handle("Review task creation", context={"project": "sample"})

    assert response.status == AgentStatus.COMPLETED
    assert response.output == "Mock QA analysis for task: Review task creation"


def test_agent_service_passes_trace_id_to_provider() -> None:
    class TraceProvider:
        def generate(self, request: AgentRequest) -> str:
            return request.trace_id or ""

    response = AgentService(TraceProvider()).handle("Trace this", trace_id="trace-123")

    assert response.output == "trace-123"


def test_service_factory_uses_configured_mock_provider() -> None:
    service = create_agent_service(Settings())

    response = service.handle("Check the task list")

    assert response.status == AgentStatus.COMPLETED
    assert response.output == "Mock QA analysis for task: Check the task list"


def test_agent_service_maps_provider_errors_to_response() -> None:
    class FailingProvider:
        def generate(self, request: AgentRequest) -> str:
            raise ProviderError("provider internals")

    response = create_agent_service(Settings(), FailingProvider()).handle("Run QA")

    assert response.status == AgentStatus.FAILED
    assert response.error_code == "provider_error"
    assert response.error_message == ProviderError.public_message


def test_agent_service_maps_unexpected_provider_errors(caplog) -> None:
    class BrokenProvider:
        def generate(self, request: AgentRequest) -> str:
            raise RuntimeError("unexpected failure")

    response = AgentService(BrokenProvider()).handle("Run QA")

    assert response.error_code == "internal_error"
    assert "Unexpected agent failure" in caplog.text


@pytest.mark.parametrize("output", ["", "  ", None, 42])
def test_agent_service_rejects_empty_or_non_text_provider_output(output: object) -> None:
    class InvalidOutputProvider:
        def generate(self, request: AgentRequest) -> object:
            return output

    response = AgentService(InvalidOutputProvider()).handle("Run QA")

    assert response.status == AgentStatus.FAILED
    assert response.error_code == "provider_error"


def test_agent_service_rejects_blank_request_before_provider_call() -> None:
    class MustNotRunProvider:
        def generate(self, request: AgentRequest) -> str:
            pytest.fail("provider must not be called for invalid request")

    service = AgentService(MustNotRunProvider())

    response = service.handle("  ")

    assert response.status == AgentStatus.FAILED
    assert response.error_code == "invalid_request"
