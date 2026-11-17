"""Requirement input and its analysis."""

from typing import Self

from pydantic import Field, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    find_duplicates,
)
from autonomous_qa_agent.models.enums import ConditionKind, Platform, Priority


class Requirement(ContractModel):
    """A product requirement or user story to be tested."""

    id: Identifier
    title: NonEmptyStr = Field(max_length=200)
    description: str = Field(default="", max_length=10_000)
    acceptance_criteria: tuple[NonEmptyStr, ...] = Field(default=(), max_length=100)
    platform: Platform
    priority: Priority = Priority.MEDIUM
    source: str | None = Field(default=None, max_length=500)  # e.g. ticket URL or file path

    @model_validator(mode="after")
    def _has_testable_content(self) -> Self:
        if not self.description and not self.acceptance_criteria:
            raise ValueError("a requirement needs a description or acceptance criteria")
        return self


class TestableCondition(ContractModel):
    """One verifiable statement derived from a requirement."""

    __test__ = False

    id: Identifier
    text: NonEmptyStr
    kind: ConditionKind


class Ambiguity(ContractModel):
    """Requirement text that cannot be tested as written, with the question to resolve it."""

    text: NonEmptyStr
    reason: NonEmptyStr
    question: NonEmptyStr


class RequirementAnalysis(ContractModel):
    """Output of the requirement analyst."""

    requirement_id: Identifier
    conditions: tuple[TestableCondition, ...] = ()
    ambiguities: tuple[Ambiguity, ...] = ()
    assumptions: tuple[NonEmptyStr, ...] = ()
    risks: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def _unique_condition_ids(self) -> Self:
        if duplicated := find_duplicates(c.id for c in self.conditions):
            raise ValueError(f"duplicate condition ids: {duplicated}")
        return self

    @property
    def is_testable(self) -> bool:
        return bool(self.conditions)

    @property
    def condition_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.conditions)
