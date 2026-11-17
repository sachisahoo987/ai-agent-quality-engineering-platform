"""Failure analysis and self-healing recommendations.

Healing recommendations are always proposals: applying any of them requires a recorded human
approval, so there is deliberately no "auto-apply" flag on the contract.
"""

from typing import Self

from pydantic import Field, model_validator

from autonomous_qa_agent.models.common import (
    Confidence,
    ContractModel,
    Identifier,
    NonEmptyStr,
)
from autonomous_qa_agent.models.enums import ActionRisk, FailureCategory, HealingAction
from autonomous_qa_agent.models.execution import Locator
from autonomous_qa_agent.models.results import EvidenceRef

_CHANGE_DESCRIPTION_REQUIRED = frozenset(
    {HealingAction.ADD_EXPLICIT_WAIT, HealingAction.UPDATE_TEST_DATA}
)


class FailureAnalysis(ContractModel):
    """Classified root cause of one failed step."""

    scenario_id: Identifier
    step_id: Identifier
    attempt: int = Field(default=1, ge=1)
    category: FailureCategory
    root_cause: NonEmptyStr = Field(max_length=2_000)
    confidence: Confidence
    evidence: tuple[EvidenceRef, ...] = ()


class HealingRecommendation(ContractModel):
    """A proposed fix for a failure, with before/after where applicable."""

    id: Identifier
    scenario_id: Identifier
    step_id: Identifier
    action: HealingAction
    rationale: NonEmptyStr = Field(max_length=2_000)
    confidence: Confidence
    risk: ActionRisk
    before: Locator | None = None
    after: Locator | None = None
    proposed_change: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.action is HealingAction.UPDATE_LOCATOR:
            if self.before is None or self.after is None:
                raise ValueError("update_locator requires both before and after locators")
            if self.before == self.after:
                raise ValueError("update_locator must change the locator")
        elif self.before is not None or self.after is not None:
            raise ValueError("before/after locators are only valid for update_locator")
        if self.action in _CHANGE_DESCRIPTION_REQUIRED and not self.proposed_change:
            raise ValueError(f"{self.action} requires a proposed_change")
        return self
