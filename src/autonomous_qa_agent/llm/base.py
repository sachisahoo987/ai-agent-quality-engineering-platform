"""Provider-independent language model interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from autonomous_qa_agent.models import AgentRequest


@runtime_checkable
class LLMProvider(Protocol):
    """Contract implemented by language model providers."""

    def generate(self, request: AgentRequest) -> str:
        """Generate a response for a validated agent request."""
