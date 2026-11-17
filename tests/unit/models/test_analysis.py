from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    ActionRisk,
    FailureAnalysis,
    FailureCategory,
    HealingAction,
    HealingRecommendation,
    Locator,
    LocatorStrategy,
)

NEW_LOCATOR = Locator(strategy=LocatorStrategy.ROLE, value="button[name=Save]")


def _recommendation(**overrides: Any) -> HealingRecommendation:
    data: dict[str, Any] = {
        "id": "HR-1",
        "scenario_id": "SC-001",
        "step_id": "step-1",
        "action": HealingAction.QUARANTINE,
        "rationale": "Flaky for 3 runs",
        "confidence": 0.6,
        "risk": ActionRisk.READ_ONLY,
    }
    return HealingRecommendation(**(data | overrides))


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_failure_analysis_confidence_bounds(confidence: float) -> None:
    with pytest.raises(ValidationError):
        FailureAnalysis(
            scenario_id="SC-001",
            step_id="step-1",
            category=FailureCategory.TIMING,
            root_cause="Spinner still visible",
            confidence=confidence,
        )


def test_update_locator_recommendation(locator: Locator) -> None:
    rec = _recommendation(action=HealingAction.UPDATE_LOCATOR, before=locator, after=NEW_LOCATOR)
    assert rec.after == NEW_LOCATOR


def test_update_locator_requires_both_locators(locator: Locator) -> None:
    with pytest.raises(ValidationError, match="both before and after"):
        _recommendation(action=HealingAction.UPDATE_LOCATOR, before=locator)


def test_update_locator_must_change_something(locator: Locator) -> None:
    with pytest.raises(ValidationError, match="must change"):
        _recommendation(action=HealingAction.UPDATE_LOCATOR, before=locator, after=locator)


def test_locators_only_allowed_for_update_locator(locator: Locator) -> None:
    with pytest.raises(ValidationError, match="only valid for update_locator"):
        _recommendation(after=locator)


@pytest.mark.parametrize(
    "action", [HealingAction.ADD_EXPLICIT_WAIT, HealingAction.UPDATE_TEST_DATA]
)
def test_change_description_required(action: HealingAction) -> None:
    with pytest.raises(ValidationError, match="requires a proposed_change"):
        _recommendation(action=action)
    assert _recommendation(action=action, proposed_change="wait for #list").proposed_change


def test_recommendation_has_no_auto_apply_switch() -> None:
    assert "requires_approval" not in HealingRecommendation.model_fields
    with pytest.raises(ValidationError):
        _recommendation(auto_apply=True)
