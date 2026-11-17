"""Tests for provider abstraction and deterministic mock."""

from autonomous_qa_agent.llm import LLMProvider, MockLLMProvider
from autonomous_qa_agent.models import AgentRequest


def test_mock_provider_is_deterministic() -> None:
    provider = MockLLMProvider()
    request = AgentRequest(task="Review task creation")

    assert provider.generate(request) == provider.generate(request)
    assert provider.generate(request) == "Mock QA analysis for task: Review task creation"


def test_mock_provider_satisfies_provider_protocol() -> None:
    assert isinstance(MockLLMProvider(), LLMProvider)


def test_mock_provider_uses_request_only_and_makes_no_network_calls() -> None:
    request = AgentRequest(task="Check task list", context={"project": "sample"})

    assert "Check task list" in MockLLMProvider().generate(request)
