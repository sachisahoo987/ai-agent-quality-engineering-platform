"""Test scenario model."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScenarioPriority(StrEnum):
    """Relative execution priority for a test scenario."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestScenario(BaseModel):
    """A test case with preconditions, actions, and observable expectations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2_000)
    steps: tuple[str, ...] = Field(min_length=1, max_length=100)
    expected_result: str = Field(min_length=1, max_length=2_000)
    priority: ScenarioPriority = ScenarioPriority.MEDIUM
    tags: tuple[str, ...] = Field(default_factory=tuple, max_length=20)

    @field_validator("title", "description", "expected_result")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only values and normalize surrounding whitespace."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must contain non-whitespace characters")
        return normalized

    @field_validator("steps", "tags")
    @classmethod
    def sequence_items_must_not_be_blank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Normalize sequence entries and reject blank items."""
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("sequence items must contain non-whitespace characters")
        return normalized
