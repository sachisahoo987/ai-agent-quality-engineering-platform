"""Build the configured LLM provider."""

from autonomous_qa_agent.config.settings import Settings
from autonomous_qa_agent.llm.mock import MockLLMProvider
from autonomous_qa_agent.models.errors import ConfigurationError
from autonomous_qa_agent.ports.llm import LLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Return the provider named by ``settings.llm_provider``."""
    match settings.llm_provider:
        case "mock":
            return MockLLMProvider()
        case unknown:  # unreachable while Settings validates the name; kept for new providers
            raise ConfigurationError(f"unsupported LLM provider: {unknown!r}")
