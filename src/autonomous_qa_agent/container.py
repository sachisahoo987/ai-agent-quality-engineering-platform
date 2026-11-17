"""Composition root: the only module that imports adapters and wires them into agents."""

from dataclasses import dataclass

from autonomous_qa_agent.agents.requirement_analyst import RequirementAnalyst
from autonomous_qa_agent.config.settings import Settings, load_settings
from autonomous_qa_agent.llm.factory import create_llm_provider
from autonomous_qa_agent.ports.llm import LLMProvider


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    llm: LLMProvider
    requirement_analyst: RequirementAnalyst


def build_container(settings: Settings | None = None) -> Container:
    """Wire the application from ``settings`` (read from the environment when omitted)."""
    settings = settings or load_settings()
    llm = create_llm_provider(settings)
    return Container(settings=settings, llm=llm, requirement_analyst=RequirementAnalyst(llm))
