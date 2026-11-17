"""Request and response models for agent interactions."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentStatus(StrEnum):
    """Lifecycle states for an agent request."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRequest(BaseModel):
    """A validated request to perform a QA task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)
    task: str = Field(min_length=1, max_length=10_000)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task")
    @classmethod
    def task_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only tasks and normalize surrounding whitespace."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("task must contain non-whitespace characters")
        return normalized

    @field_validator("trace_id")
    @classmethod
    def trace_id_must_not_be_blank(cls, value: str | None) -> str | None:
        """Normalize an optional trace identifier and reject whitespace-only values."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("trace_id must contain non-whitespace characters")
        return normalized


class AgentResponse(BaseModel):
    """A structured result or safe error response for an agent request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: UUID
    correlation_id: UUID
    status: AgentStatus
    output: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> AgentResponse:
        """Ensure success and failure payloads are internally consistent."""
        if self.status is AgentStatus.COMPLETED:
            if self.output is None or self.error_code is not None or self.error_message is not None:
                raise ValueError(
                    "completed responses require output and cannot include error fields"
                )
        elif self.status is AgentStatus.FAILED:
            if self.error_code is None or self.error_message is None or self.output is not None:
                raise ValueError("failed responses require error fields and cannot include output")
        else:
            raise ValueError("responses must have completed or failed status")
        return self
