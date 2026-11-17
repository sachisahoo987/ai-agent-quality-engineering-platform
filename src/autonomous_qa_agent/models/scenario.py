"""Test scenarios: human-readable, traceable to requirement conditions."""

from typing import Self

from pydantic import Field, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    find_duplicates,
)
from autonomous_qa_agent.models.enums import Priority, Technique


class TestScenario(ContractModel):
    """A test case with preconditions, steps and observable expectations.

    ``traces_to`` links the scenario to the requirement conditions it verifies; a scenario that
    verifies nothing is rejected.
    """

    __test__ = False

    id: Identifier
    requirement_id: Identifier
    title: NonEmptyStr = Field(max_length=200)
    technique: Technique
    priority: Priority = Priority.MEDIUM
    preconditions: tuple[NonEmptyStr, ...] = Field(default=(), max_length=50)
    steps: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=100)
    expected_results: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=50)
    traces_to: tuple[Identifier, ...] = Field(min_length=1)
    tags: tuple[NonEmptyStr, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def _unique_traces(self) -> Self:
        if duplicated := find_duplicates(self.traces_to):
            raise ValueError(f"duplicate condition ids in traces_to: {duplicated}")
        return self
