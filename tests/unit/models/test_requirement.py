import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    Ambiguity,
    ConditionKind,
    Platform,
    Priority,
    Requirement,
    RequirementAnalysis,
    TestableCondition,
)


def test_requirement_defaults_and_normalisation() -> None:
    req = Requirement(
        id="REQ-1",
        title="  Create task  ",
        acceptance_criteria=("  Title is required ",),
        platform=Platform.WEB,
    )
    assert req.title == "Create task"
    assert req.acceptance_criteria == ("Title is required",)
    assert req.priority is Priority.MEDIUM


def test_requirement_needs_description_or_criteria() -> None:
    with pytest.raises(ValidationError, match="description or acceptance criteria"):
        Requirement(id="REQ-1", title="Empty", platform=Platform.WEB)


@pytest.mark.parametrize("bad_id", ["", "  ", "has space", "-leading-dash", "x" * 129])
def test_requirement_rejects_bad_identifiers(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        Requirement(id=bad_id, title="t", description="d", platform=Platform.WEB)


def test_requirement_rejects_blank_criteria_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Requirement(id="R", title="t", acceptance_criteria=("  ",), platform=Platform.WEB)
    with pytest.raises(ValidationError):
        Requirement(id="R", title="t", description="d", platform=Platform.WEB, owner="me")


def test_requirement_is_immutable() -> None:
    req = Requirement(id="R", title="t", description="d", platform=Platform.WEB)
    with pytest.raises(ValidationError):
        req.title = "changed"  # type: ignore[misc]


def test_analysis_exposes_conditions() -> None:
    analysis = RequirementAnalysis(
        requirement_id="REQ-1",
        conditions=(
            TestableCondition(id="C-1", text="Title required", kind=ConditionKind.NEGATIVE),
            TestableCondition(id="C-2", text="Max 120 chars", kind=ConditionKind.BOUNDARY),
        ),
        ambiguities=(Ambiguity(text="fast", reason="not measurable", question="How fast?"),),
    )
    assert analysis.is_testable
    assert analysis.condition_ids == {"C-1", "C-2"}


def test_analysis_without_conditions_is_not_testable() -> None:
    assert not RequirementAnalysis(requirement_id="REQ-1").is_testable


def test_analysis_rejects_duplicate_condition_ids() -> None:
    cond = TestableCondition(id="C-1", text="x", kind=ConditionKind.FUNCTIONAL)
    with pytest.raises(ValidationError, match="duplicate condition ids"):
        RequirementAnalysis(requirement_id="REQ-1", conditions=(cond, cond))
