"""Regression tests on the real requirement examples in ``examples/requirements``.

Each example pins what the analyst must find, how findings are categorised (stated condition,
derived or domain test idea, mandatory or recommended clarification) and that every finding
traces back to a condition and to the original text.
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from autonomous_qa_agent.agents import RequirementAnalyst
from autonomous_qa_agent.llm import MockLLMProvider
from autonomous_qa_agent.models import (
    AgentStatus,
    AmbiguityKind,
    ConditionKind,
    Provenance,
    QualityAttribute,
    Requirement,
    RequirementAnalysis,
    RiskCategory,
)

EXAMPLES = Path(__file__).parents[3] / "examples" / "requirements"
ALL_EXAMPLES = sorted(p.stem for p in EXAMPLES.glob("*.json"))
REQUIREMENT_LEVEL_TOPICS = {"Acceptance criteria", "Expected behaviour"}


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def analyse(name: str) -> RequirementAnalysis:
    return RequirementAnalyst.analyse_with_rules(Requirement.model_validate(load(name)))


async def status(name: str) -> AgentStatus:
    return (await RequirementAnalyst(MockLLMProvider()).run(load(name))).status


def ideas_by_rule(analysis: RequirementAnalysis, rule: str) -> list[str]:
    return [i.text for i in analysis.test_ideas if i.rule == rule]


def recommendations(analysis: RequirementAnalysis) -> dict[str, str | None]:
    return {a.text: a.condition_id for a in analysis.recommendations}


# ------------------------------------------------------------------ Test 1: banking login
async def test_banking_login_is_one_stated_condition_with_its_original_text() -> None:
    analysis = analyse("banking-login")
    description = load("banking-login")["description"]

    (condition,) = analysis.conditions
    assert condition.id == "C-1"
    assert condition.kind is ConditionKind.FUNCTIONAL
    assert condition.text == condition.source_text == description  # not split: noun list
    assert condition.source_location == "description"
    assert await status("banking-login") is AgentStatus.COMPLETED


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("otp_verification", "invalid OTP"),
        ("otp_verification", "expired OTP"),
        ("otp_verification", "Resending the OTP"),
        ("otp_verification", "attempt limit"),
        ("otp_verification", "network failure"),
        ("mobile_number_input", "invalid format"),
        ("mobile_number_input", "shorter and one digit longer"),
        ("authentication_session", "session expires"),
    ],
)
def test_banking_login_domain_test_ideas(rule: str, expected: str) -> None:
    assert any(expected in text for text in ideas_by_rule(analyse("banking-login"), rule))


def test_banking_login_domain_findings_are_ideas_not_requirements() -> None:
    analysis = analyse("banking-login")
    assert all(i.provenance is Provenance.DOMAIN_PRACTICE for i in analysis.test_ideas)
    assert all(i.condition_id == "C-1" for i in analysis.test_ideas)
    assert len(analysis.conditions) == 1  # no domain scenario became a condition


def test_banking_login_recommends_the_unstated_details() -> None:
    analysis = analyse("banking-login")
    assert recommendations(analysis) == {
        "OTP validity period": "C-1",
        "OTP attempt limit": "C-1",
        "OTP resend rules": "C-1",
        "Mobile number format": "C-1",
        "Session timeout": "C-1",
        "Acceptance criteria": None,
    }
    assert analysis.mandatory_clarifications == ()


def test_banking_login_risks_and_dependencies() -> None:
    analysis = analyse("banking-login")
    assert {r.category for r in analysis.risks} == {
        RiskCategory.SECURITY,
        RiskCategory.INTEGRATION,
        RiskCategory.PRIVACY,
        RiskCategory.BUSINESS_IMPACT,
    }
    assert all(r.condition_ids == ("C-1",) for r in analysis.risks)
    assert analysis.dependencies == (
        "SMS / one-time-passcode provider",
        "Authentication / identity service",
    )


# ------------------------------------------------------------------ Test 2: e-commerce checkout
async def test_checkout_is_decomposed_into_one_condition_per_action() -> None:
    analysis = analyse("checkout")
    description = load("checkout")["description"]

    assert [(c.id, c.text) for c in analysis.conditions] == [
        ("C-1.1", "A customer should be able to add products to the cart."),
        ("C-1.2", "A customer should be able to apply a discount coupon."),
        ("C-1.3", "A customer should be able to complete payment."),
    ]
    assert all(c.source_text == description for c in analysis.conditions)
    assert all(c.kind is ConditionKind.FUNCTIONAL for c in analysis.conditions)
    assert await status("checkout") is AgentStatus.COMPLETED


@pytest.mark.parametrize(
    ("condition_id", "rule", "expected"),
    [
        ("C-1.1", "cart", "Cart quantities at the boundaries"),
        ("C-1.2", "coupon", "invalid coupon"),
        ("C-1.2", "coupon", "expired coupon"),
        ("C-1.2", "coupon", "already-used"),
        ("C-1.2", "coupon", "minimum cart value"),
        ("C-1.3", "payment", "declined payment"),
        ("C-1.3", "payment", "charges the customer only once"),
    ],
)
def test_checkout_domain_ideas_trace_to_the_right_action(
    condition_id: str, rule: str, expected: str
) -> None:
    analysis = analyse("checkout")
    ideas = [i for i in analysis.test_ideas if i.rule == rule]
    assert ideas
    assert {i.condition_id for i in ideas} == {condition_id}
    assert any(expected in i.text for i in ideas)


def test_checkout_test_idea_ids_are_scoped_to_their_condition() -> None:
    analysis = analyse("checkout")
    for idea in analysis.test_ideas:
        assert idea.id.startswith(f"{idea.condition_id}:T-")
    assert [i.id for i in analysis.test_ideas_for("C-1.3")] == [
        f"C-1.3:T-{n}" for n in (1, 2, 3, 4)
    ]


def test_checkout_risks_reference_the_actions_that_raise_them() -> None:
    risks = {(r.category, r.condition_ids) for r in analyse("checkout").risks}
    assert risks == {
        (RiskCategory.FINANCIAL, ("C-1.2",)),
        (RiskCategory.FINANCIAL, ("C-1.3",)),
        (RiskCategory.INTEGRATION, ("C-1.3",)),
    }


def test_checkout_recommendations_are_per_action() -> None:
    assert recommendations(analyse("checkout")) == {
        "Cart quantity limits": "C-1.1",
        "Coupon rules": "C-1.2",
        "Payment methods": "C-1.3",
        "Payment failure handling": "C-1.3",
        "Acceptance criteria": None,
    }


# ------------------------------------------------------------------ Test 3: ambiguous load time
async def test_load_time_is_non_functional_performance() -> None:
    analysis = analyse("load-time")
    (condition,) = analysis.conditions
    assert condition.kind is ConditionKind.NON_FUNCTIONAL
    assert condition.quality_attributes == (QualityAttribute.PERFORMANCE,)
    assert analysis.non_functional_conditions == (condition,)
    assert await status("load-time") is AgentStatus.NEEDS_CLARIFICATION


def test_load_time_threshold_is_a_mandatory_missing_criterion() -> None:
    (mandatory,) = analyse("load-time").mandatory_clarifications
    assert mandatory.kind is AmbiguityKind.MISSING
    assert mandatory.text == "Performance threshold"
    assert mandatory.condition_id == "C-1"
    assert "'quickly'" in mandatory.reason


def test_load_time_gets_no_irrelevant_clarifications_or_domain_ideas() -> None:
    analysis = analyse("load-time")
    topics = {a.text for a in analysis.ambiguities}
    assert topics == {"Performance threshold", "Acceptance criteria"}
    assert all(i.provenance is Provenance.DERIVED for i in analysis.test_ideas)


# ------------------------------------------------------------------ every example
@pytest.mark.parametrize("name", ALL_EXAMPLES)
def test_every_finding_traces_to_a_condition(name: str) -> None:
    analysis = analyse(name)
    ids = analysis.condition_ids
    assert all(i.condition_id in ids for i in analysis.test_ideas)
    assert all(set(r.condition_ids) <= ids for r in analysis.risks)
    for ambiguity in analysis.ambiguities:
        if ambiguity.condition_id is None:
            assert (
                ambiguity.text in REQUIREMENT_LEVEL_TOPICS
                or ambiguity.text.endswith(" expectation")  # implied by the title
                or ambiguity.text == load(name)["title"]
            )
        else:
            assert ambiguity.condition_id in ids


@pytest.mark.parametrize("name", ALL_EXAMPLES)
def test_conditions_preserve_the_original_text(name: str) -> None:
    data = load(name)
    stated = " ".join([data.get("description", ""), *data.get("acceptance_criteria", [])])
    for condition in analyse(name).conditions:
        assert condition.source_text in stated
        # a decomposed clause only uses words from its source statement
        assert set(re.findall(r"\w+", condition.text.lower())) <= set(
            re.findall(r"\w+", condition.source_text.lower())
        )


@pytest.mark.parametrize("name", ALL_EXAMPLES)
def test_no_invented_numbers(name: str) -> None:
    """Every number in the analysis (outside ids) already appears in the requirement."""
    data = load(name)
    stated_numbers = set(re.findall(r"\d+", json.dumps(data)))
    analysis = analyse(name).model_dump(mode="json")
    texts: list[str] = []
    for section in ("conditions", "test_ideas", "ambiguities", "risks"):
        for item in analysis[section]:
            texts += [
                value
                for key, value in item.items()
                if isinstance(value, str) and not key.endswith("id") and key != "source_location"
            ]
    texts += analysis["assumptions"]
    invented = {n for text in texts for n in re.findall(r"\d+", text)} - stated_numbers
    assert invented == set()
