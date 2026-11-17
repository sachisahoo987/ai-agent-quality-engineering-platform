import pytest

from autonomous_qa_agent.config import Settings
from autonomous_qa_agent.llm import MockLLMProvider, create_llm_provider
from autonomous_qa_agent.models import ConfigurationError, ProviderError
from autonomous_qa_agent.ports import LLMProvider, LLMRequest


def request(task: str = "summary") -> LLMRequest:
    return LLMRequest(task=task, system="You are a tester.", prompt="Summarise the run.")


async def test_mock_answers_empty_json_by_default_and_records_requests() -> None:
    llm = MockLLMProvider()
    response = await llm.complete(request())

    assert response.text == "{}"
    assert response.model == "mock-1"
    assert response.input_tokens == 7
    assert llm.requests == [request()]


async def test_mock_scripted_responses_per_task() -> None:
    llm = MockLLMProvider({"summary": "All passed."}, default="fallback")
    assert (await llm.complete(request())).text == "All passed."
    assert (await llm.complete(request("other"))).text == "fallback"


async def test_mock_configured_failure_raises_provider_error() -> None:
    llm = MockLLMProvider(failures=frozenset({"summary"}))
    with pytest.raises(ProviderError, match="summary"):
        await llm.complete(request())
    assert len(llm.requests) == 1


def test_mock_satisfies_the_port() -> None:
    assert isinstance(MockLLMProvider(), LLMProvider)
    assert MockLLMProvider().name == "mock"


def test_factory_builds_the_mock_provider() -> None:
    assert isinstance(create_llm_provider(Settings()), MockLLMProvider)


def test_factory_rejects_unknown_providers() -> None:
    settings = Settings.model_construct(llm_provider="unknown")  # bypasses validation
    with pytest.raises(ConfigurationError, match="unknown"):
        create_llm_provider(settings)
