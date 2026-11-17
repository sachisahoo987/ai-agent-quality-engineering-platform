"""Interfaces (``Protocol``s) that agents depend on. Adapters live in ``llm`` and ``tools``."""

from autonomous_qa_agent.ports.llm import LLMProvider, LLMRequest, LLMResponse
from autonomous_qa_agent.ports.structured import generate_structured, parse_structured

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "generate_structured",
    "parse_structured",
]
