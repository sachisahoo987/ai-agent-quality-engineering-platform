"""Human-in-the-loop approval contracts."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    find_duplicates,
)
from autonomous_qa_agent.models.enums import ActionRisk, ApprovalKind


class ApprovalItem(ContractModel):
    """One thing being approved: a risky plan step or a healing recommendation."""

    ref: Identifier  # step id or recommendation id
    scenario_id: Identifier | None = None
    summary: NonEmptyStr = Field(max_length=500)
    risk: ActionRisk


class ApprovalRequest(ContractModel):
    """Raised when the workflow pauses for a decision. Approval is all-or-nothing."""

    id: Identifier
    run_id: UUID
    kind: ApprovalKind
    items: tuple[ApprovalItem, ...] = Field(min_length=1)
    created_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        if duplicated := find_duplicates(i.ref for i in self.items):
            raise ValueError(f"duplicate approval item refs: {duplicated}")
        return self

    def is_expired(self, now: datetime) -> bool:
        """An expired request must be treated as rejected."""
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return now >= self.expires_at


class ApprovalDecision(ContractModel):
    """The recorded human decision; a rejection must say why."""

    request_id: Identifier
    approved: bool
    approver: NonEmptyStr = Field(max_length=200)
    reason: str | None = Field(default=None, max_length=2_000)
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def _rejection_has_reason(self) -> Self:
        if not self.approved and not self.reason:
            raise ValueError("a rejection requires a reason")
        return self
