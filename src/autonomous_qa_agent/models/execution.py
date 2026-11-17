"""Test execution result models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionStatus(StrEnum):
    """Outcome of executing a test scenario."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestExecutionResult(BaseModel):
    """The recorded outcome and timing for a single scenario execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: UUID = Field(default_factory=uuid4)
    scenario_id: UUID
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime
    duration_seconds: float = Field(ge=0)
    details: str | None = Field(default=None, max_length=4_000)
    evidence: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @model_validator(mode="after")
    def validate_timestamps(self) -> TestExecutionResult:
        """Require timezone-aware timestamps in chronological order."""
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("execution timestamps must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self
