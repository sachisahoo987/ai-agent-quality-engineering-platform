"""Deterministic local provider used for development and tests."""

from autonomous_qa_agent.models import AgentRequest


class MockLLMProvider:
    """Return stable output without network or external model dependencies."""

    def generate(self, request: AgentRequest) -> str:
        """Create a deterministic response containing the requested task."""
        return f"Mock QA analysis for task: {request.task}"
