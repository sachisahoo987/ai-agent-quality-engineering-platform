"""Context-aware clarifications: asked only where they apply, skipped when already answered."""

from typing import Any

import pytest

from autonomous_qa_agent.agents.requirement_rules import analyse
from autonomous_qa_agent.models import (
    AmbiguityKind,
    Necessity,
    Platform,
    Requirement,
    RequirementAnalysis,
)


def analysis_of(*criteria: str, **fields: Any) -> RequirementAnalysis:
    data: dict[str, Any] = {
        "id": "REQ-1",
        "title": "Requirement",
        "platform": Platform.WEB,
        "acceptance_criteria": criteria,
    }
    return analyse(Requirement(**(data | fields))).freeze()


def topics(analysis: RequirementAnalysis) -> set[str]:
    return {a.text for a in analysis.ambiguities}


def test_generic_input_checks_apply_to_input_without_a_feature_rule() -> None:
    analysis = analysis_of("The user can enter a display name")
    gaps = {a.text: a for a in analysis.ambiguities}
    assert {"Invalid-input handling", "Input limits"} <= gaps.keys()
    assert all(gaps[t].necessity is Necessity.RECOMMENDED for t in ("Input limits",))
    assert gaps["Input limits"].condition_id == "C-1"


def test_stated_negative_criterion_answers_invalid_input_handling() -> None:
    analysis = analysis_of(
        "The user can enter a display name", "An invalid display name shows an error"
    )
    assert "Invalid-input handling" not in topics(analysis)


def test_stated_limit_answers_input_limits() -> None:
    analysis = analysis_of("The user can enter a display name of at most 30 characters")
    assert "Input limits" not in topics(analysis)
    assert any(i.rule == "stated_limit" for i in analysis.test_ideas)


@pytest.mark.parametrize(
    "criterion",
    [
        "The application should load quickly.",  # non-functional
        "Users can view their order history.",  # no input
        "Users can log in with a mobile number and OTP.",  # covered by feature rules
    ],
)
def test_generic_input_checks_do_not_apply_elsewhere(criterion: str) -> None:
    assert {"Invalid-input handling", "Input limits"}.isdisjoint(topics(analysis_of(criterion)))


@pytest.mark.parametrize(
    ("criteria", "answered"),
    [
        (("Users log in with an OTP", "The OTP expires after 5 minutes"), "OTP validity period"),
        (("Users log in with an OTP", "Allow 3 invalid attempts"), "OTP attempt limit"),
        (("Users log in with an OTP", "An OTP can be resent after 30 seconds"), "OTP resend rules"),
        (("Users log in with a mobile number of 10 digits",), "Mobile number format"),
        (("Users log in", "The session expires after 15 minutes of inactivity"), "Session timeout"),
        (("Customers can add up to 10 items to the cart",), "Cart quantity limits"),
        (("Customers pay by Visa or PayPal",), "Payment methods"),
    ],
)
def test_domain_clarifications_are_skipped_when_the_text_answers_them(
    criteria: tuple[str, ...], answered: str
) -> None:
    assert answered not in topics(analysis_of(*criteria))


def test_domain_clarifications_are_recommended_and_missing() -> None:
    analysis = analysis_of("Customers can apply a coupon")
    (coupon,) = [a for a in analysis.ambiguities if a.text == "Coupon rules"]
    assert (coupon.kind, coupon.necessity, coupon.condition_id) == (
        AmbiguityKind.MISSING,
        Necessity.RECOMMENDED,
        "C-1",
    )


def test_same_clarification_from_two_conditions_is_asked_once() -> None:
    analysis = analysis_of("Customers can pay by card", "Guests can pay at checkout")
    assert [a.condition_id for a in analysis.ambiguities if a.text == "Payment methods"] == ["C-1"]
    payment_ideas = {i.condition_id for i in analysis.test_ideas if i.rule == "payment"}
    assert payment_ideas == {"C-1", "C-2"}  # each condition still needs its own tests


@pytest.mark.parametrize(
    ("criterion", "term"),
    [
        ("The list shows some recent orders", "'some'"),
        ("Users can export reports etc", "'etc'"),
        ("Errors are handled properly", "'properly'"),
    ],
)
def test_unverifiable_wording_is_mandatory_and_tied_to_its_condition(
    criterion: str, term: str
) -> None:
    (mandatory,) = analysis_of(criterion).mandatory_clarifications
    assert mandatory.kind is AmbiguityKind.AMBIGUOUS
    assert mandatory.text == criterion
    assert mandatory.condition_id == "C-1"
    assert term in mandatory.reason


def test_vague_title_is_flagged_once_when_the_body_does_not_ask() -> None:
    analysis = analysis_of("Users can save a draft", title="Save several drafts")
    assert [(a.text, a.condition_id) for a in analysis.mandatory_clarifications] == [
        ("Save several drafts", None)
    ]
    repeated = analysis_of("Users can save several drafts", title="Several drafts")
    assert [a.text for a in repeated.mandatory_clarifications] == ["Users can save several drafts"]


def test_title_identical_to_a_condition_is_not_checked_twice() -> None:
    analysis = analysis_of("Users can save several drafts", title="Users can save several drafts")
    assert len(analysis.mandatory_clarifications) == 1


def test_missing_acceptance_criteria_is_only_a_recommendation_when_testable() -> None:
    testable = analysis_of(description="Users can save a draft.")
    (gap,) = [a for a in testable.ambiguities if a.text == "Acceptance criteria"]
    assert gap.necessity is Necessity.RECOMMENDED
    untestable = analysis_of(description="Drafts.")
    (gap,) = [a for a in untestable.ambiguities if a.text == "Acceptance criteria"]
    assert gap.necessity is Necessity.MANDATORY


def test_unclear_requirement_risk_lists_only_the_unclear_conditions() -> None:
    analysis = analysis_of("Users can save a draft", "The list shows some drafts")
    (risk,) = [r for r in analysis.risks if r.category == "unclear_requirement"]
    assert risk.condition_ids == ("C-2",)
