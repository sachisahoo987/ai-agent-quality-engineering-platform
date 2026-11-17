"""Execution results and evidence."""

from typing import Self

from pydantic import AwareDatetime, Field, JsonValue, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    find_duplicates,
)
from autonomous_qa_agent.models.enums import EvidenceKind, TestStatus


class EvidenceRef(ContractModel):
    """Pointer to captured evidence (stored by the artifact store, not inline)."""

    kind: EvidenceKind
    uri: NonEmptyStr
    captured_at: AwareDatetime | None = None


class ExecutionError(ContractModel):
    """Normalised error from a tool call or assertion."""

    type: NonEmptyStr  # e.g. "TimeoutError", "AssertionFailed", "ElementNotFound"
    message: str = Field(max_length=4_000)
    tool: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class StepResult(ContractModel):
    """Outcome of one executable step. Duration is derived from timestamps, never stored."""

    step_id: Identifier
    status: TestStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime
    error: ExecutionError | None = None
    evidence: tuple[EvidenceRef, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.status.is_failure and self.error is None:
            raise ValueError("a failed or errored step must include an error")
        if not self.status.is_failure and self.error is not None:
            raise ValueError("only a failed or errored step may include an error")
        return self

    @property
    def duration_ms(self) -> int:
        return round((self.finished_at - self.started_at).total_seconds() * 1000)


class TestResult(ContractModel):
    """Outcome of one attempt at one planned test."""

    __test__ = False

    scenario_id: Identifier
    attempt: int = Field(default=1, ge=1)
    status: TestStatus
    steps: tuple[StepResult, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if duplicated := find_duplicates(s.step_id for s in self.steps):
            raise ValueError(f"duplicate step ids: {duplicated}")
        if self.status is TestStatus.PASSED and (
            not self.steps or any(s.status is not TestStatus.PASSED for s in self.steps)
        ):
            raise ValueError("a passed test needs at least one step and every step passed")
        if any(s.status.is_failure for s in self.steps) and not self.status.is_failure:
            raise ValueError("a test with a failed or errored step must be failed or errored")
        return self

    @property
    def first_failure(self) -> StepResult | None:
        return next((s for s in self.steps if s.status.is_failure), None)

    @property
    def duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.steps)
