from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    Ambiguity,
    AmbiguityKind,
    ConditionKind,
    Necessity,
    Platform,
    Priority,
    Provenance,
    QualityAttribute,
    Requirement,
    RequirementAnalysis,
    Risk,
    RiskCategory,
    TestableCondition,
    TestIdea,
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


def condition(cid: str = "C-1", **overrides: Any) -> TestableCondition:
    data: dict[str, Any] = {
        "id": cid,
        "text": "Create a task",
        "kind": ConditionKind.FUNCTIONAL,
        "source_text": "Create a task",
        "source_location": "acceptance_criteria[0]",
    }
    return TestableCondition(**(data | overrides))


def idea(iid: str = "C-1:T-1", condition_id: str = "C-1", **overrides: Any) -> TestIdea:
    data: dict[str, Any] = {
        "id": iid,
        "condition_id": condition_id,
        "text": "Blank title is rejected",
        "kind": ConditionKind.NEGATIVE,
        "provenance": Provenance.DOMAIN_PRACTICE,
    }
    return TestIdea(**(data | overrides))


def risk(*condition_ids: str) -> Risk:
    return Risk(
        text="Data loss",
        category=RiskCategory.DATA_LOSS,
        condition_ids=condition_ids,
        provenance=Provenance.DERIVED,
    )


# ------------------------------------------------------------------ conditions
def test_condition_keeps_its_source() -> None:
    cond = condition(text="Users can add items", source_text="Users can add and remove items")
    assert cond.source_text == "Users can add and remove items"
    with pytest.raises(ValidationError):
        condition(source_text=" ")
    with pytest.raises(ValidationError):
        TestableCondition(id="C-1", text="x", kind=ConditionKind.FUNCTIONAL)  # type: ignore[call-arg]


def test_non_functional_condition_needs_a_quality_attribute() -> None:
    nfr = condition(
        kind=ConditionKind.NON_FUNCTIONAL, quality_attributes=(QualityAttribute.PERFORMANCE,)
    )
    assert nfr.quality_attributes == (QualityAttribute.PERFORMANCE,)
    with pytest.raises(ValidationError, match="needs at least one quality attribute"):
        condition(kind=ConditionKind.NON_FUNCTIONAL)
    with pytest.raises(ValidationError, match="only valid on non_functional"):
        condition(quality_attributes=(QualityAttribute.SECURITY,))


# ------------------------------------------------------------------ analysis
def test_analysis_exposes_conditions() -> None:
    analysis = RequirementAnalysis(
        requirement_id="REQ-1", conditions=(condition(), condition("C-2"))
    )
    assert analysis.is_testable
    assert analysis.condition_ids == {"C-1", "C-2"}


def test_analysis_without_conditions_is_not_testable_and_needs_clarification() -> None:
    analysis = RequirementAnalysis(requirement_id="REQ-1")
    assert not analysis.is_testable
    assert analysis.needs_clarification


def test_analysis_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate condition ids"):
        RequirementAnalysis(requirement_id="REQ-1", conditions=(condition(), condition()))
    with pytest.raises(ValidationError, match="duplicate test idea ids"):
        RequirementAnalysis(
            requirement_id="REQ-1", conditions=(condition(),), test_ideas=(idea(), idea())
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"test_ideas": (idea(condition_id="C-9"),)},
        {"ambiguities": (Ambiguity(text="t", reason="r", question="q", condition_id="C-9"),)},
        {"risks": (risk("C-1", "C-9"),)},
    ],
    ids=["test-idea", "ambiguity", "risk"],
)
def test_analysis_rejects_references_to_unknown_conditions(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match=r"unknown condition ids: \['C-9'\]"):
        RequirementAnalysis(requirement_id="REQ-1", conditions=(condition(),), **fields)


def test_risk_must_reference_a_condition() -> None:
    with pytest.raises(ValidationError):
        risk()


def test_ambiguity_defaults_to_a_mandatory_requirement_level_question() -> None:
    ambiguity = Ambiguity(text="fast", reason="vague", question="How fast?")
    assert ambiguity.kind is AmbiguityKind.AMBIGUOUS
    assert ambiguity.necessity is Necessity.MANDATORY
    assert ambiguity.condition_id is None


def test_analysis_groups_findings() -> None:
    nfr = condition(
        "C-2",
        kind=ConditionKind.NON_FUNCTIONAL,
        quality_attributes=(QualityAttribute.PERFORMANCE,),
    )
    analysis = RequirementAnalysis(
        requirement_id="REQ-1",
        conditions=(condition(), nfr),
        test_ideas=(
            idea(),
            idea("C-1:T-2", kind=ConditionKind.BOUNDARY),
            idea("C-2:T-1", "C-2", kind=ConditionKind.NON_FUNCTIONAL),
        ),
        ambiguities=(
            Ambiguity(text="Performance threshold", reason="r", question="How fast?",
                      kind=AmbiguityKind.MISSING, condition_id="C-2"),
            Ambiguity(text="Coupon rules", reason="r", question="Which rules?",
                      kind=AmbiguityKind.MISSING, necessity=Necessity.RECOMMENDED),
        ),
        risks=(risk("C-1"),),
    )  # fmt: skip
    assert [c.id for c in analysis.functional_conditions] == ["C-1"]
    assert analysis.non_functional_conditions == (nfr,)
    assert [i.id for i in analysis.edge_cases] == ["C-1:T-1", "C-1:T-2"]
    assert [i.id for i in analysis.test_ideas_for("C-2")] == ["C-2:T-1"]
    assert [a.text for a in analysis.missing_criteria] == ["Performance threshold", "Coupon rules"]
    assert [a.text for a in analysis.mandatory_clarifications] == ["Performance threshold"]
    assert [a.text for a in analysis.recommendations] == ["Coupon rules"]
    assert analysis.needs_clarification


def test_recommendations_alone_do_not_block_testing() -> None:
    analysis = RequirementAnalysis(
        requirement_id="REQ-1",
        conditions=(condition(),),
        ambiguities=(
            Ambiguity(text="t", reason="r", question="q", necessity=Necessity.RECOMMENDED),
        ),
    )
    assert not analysis.needs_clarification
