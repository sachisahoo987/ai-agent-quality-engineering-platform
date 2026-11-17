"""Provider-independent language model interface.

Agents build an ``LLMRequest`` and receive an ``LLMResponse``; they never import a vendor SDK.
Providers raise ``ProviderError`` for every failure (network, quota, refusal, timeout) so that
agents need to handle a single error type.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from autonomous_qa_agent.models.common import ContractModel, Identifier, NonEmptyStr


class LLMRequest(ContractModel):
    """One completion request.

    ``task`` is a stable name for the kind of request (``requirement_analysis``). Providers may
    use it for routing or metrics, and the mock provider uses it to pick a canned response.
    ``response_schema`` is the JSON schema the answer must match, when structured output is
    wanted.
    """

    task: Identifier
    system: NonEmptyStr
    prompt: NonEmptyStr
    response_schema: dict[str, Any] | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=2_000, ge=1, le=100_000)


class LLMResponse(ContractModel):
    text: str
    model: NonEmptyStr
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


@runtime_checkable
class LLMProvider(Protocol):
    """A language model backend."""

    @property
    def name(self) -> str: ...

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Return the model's answer, or raise ``ProviderError``."""
        ...
