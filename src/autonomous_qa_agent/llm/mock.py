"""Deterministic, offline LLM provider: the default runtime provider and the test double."""

from collections.abc import Mapping

from autonomous_qa_agent.models.errors import ProviderError
from autonomous_qa_agent.ports.llm import LLMRequest, LLMResponse

EMPTY_JSON = "{}"


class MockLLMProvider:
    """Returns a fixed answer per ``task`` and records every request.

    With no configuration it answers ``{}`` to every request. For structured tasks that means
    "nothing to add", so agents return their rule-based result unchanged. Pass ``responses``
    to script answers per task, or ``failures`` to make a task raise ``ProviderError``.
    """

    def __init__(
        self,
        responses: Mapping[str, str] | None = None,
        *,
        default: str = EMPTY_JSON,
        failures: frozenset[str] = frozenset(),
    ) -> None:
        self._responses = dict(responses or {})
        self._default = default
        self._failures = failures
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "mock"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if request.task in self._failures:
            raise ProviderError(f"mock provider configured to fail task {request.task!r}")
        text = self._responses.get(request.task, self._default)
        return LLMResponse(
            text=text,
            model="mock-1",
            input_tokens=len(request.system.split()) + len(request.prompt.split()),
            output_tokens=len(text.split()),
        )
