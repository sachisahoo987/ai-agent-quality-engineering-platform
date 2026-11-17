import re

import pytest

from autonomous_qa_agent.agents.requirement_rules import analyse
from autonomous_qa_agent.agents.requirement_rules.domains import DOMAIN_RULES
from autonomous_qa_agent.agents.requirement_rules.quality import (
    QUALITY_RULES,
    quality_attributes,
)
from autonomous_qa_agent.models import (
    AmbiguityKind,
    ConditionKind,
    Necessity,
    Platform,
    QualityAttribute,
    Requirement,
)

P, S, R, A, SEC, U = (
    QualityAttribute.PERFORMANCE,
    QualityAttribute.SCALABILITY,
    QualityAttribute.RELIABILITY,
    QualityAttribute.AVAILABILITY,
    QualityAttribute.SECURITY,
    QualityAttribute.USABILITY,
)


def analysis_of(*criteria: str, title: str = "Requirement") -> object:
    return analyse(
        Requirement(id="REQ-1", title=title, platform=Platform.WEB, acceptance_criteria=criteria)
    ).freeze()


@pytest.mark.parametrize(
    ("text", "attributes"),
    [
        ("The application should load quickly.", (P,)),
        ("Search results must appear within 2 seconds.", ()),  # no indicator word; see below
        ("The page response time must be short.", (P,)),
        ("The platform must be scalable for peak load.", (S,)),
        ("Payments must be processed reliably.", (R,)),
        ("The service must have high availability.", (A,)),
        ("Card data must be stored securely.", (SEC,)),
        ("The form should be intuitive.", (U,)),
        ("Search should be fast and user-friendly.", (P, U)),
    ],
)
def test_quality_attribute_classification(
    text: str, attributes: tuple[QualityAttribute, ...]
) -> None:
    assert quality_attributes(text) == attributes


@pytest.mark.parametrize(
    "text",
    [
        "Only products available in stock are listed.",
        "Users can recover their password by email.",
        "Users can rate a film on a scale.",
        "Users can upload a file.",
    ],
)
def test_functional_wording_is_not_mistaken_for_a_quality_attribute(text: str) -> None:
    assert quality_attributes(text) == ()


def test_nfr_without_threshold_gets_one_mandatory_question_per_attribute() -> None:
    analysis = analysis_of("Search should be fast and user-friendly.")
    (condition,) = analysis.conditions
    assert condition.kind is ConditionKind.NON_FUNCTIONAL
    assert [(a.text, a.necessity, a.kind) for a in analysis.mandatory_clarifications] == [
        ("Performance threshold", Necessity.MANDATORY, AmbiguityKind.MISSING),
        ("Usability threshold", Necessity.MANDATORY, AmbiguityKind.MISSING),
    ]


@pytest.mark.parametrize(
    "criterion",
    [
        "Pages load quickly, within 2 seconds at p95.",
        "The system must scale to 10,000 concurrent users.",
        "The service must be highly available with 99.9% uptime.",
        "Card data must be encrypted with AES-256.",
        "Checkout should be easy: at most 3 steps.",
        "Orders are processed reliably with an error rate below 0.1%.",
    ],
)
def test_stated_threshold_needs_no_clarification(criterion: str) -> None:
    analysis = analysis_of(criterion)
    assert analysis.conditions[0].kind is ConditionKind.NON_FUNCTIONAL
    assert analysis.mandatory_clarifications == ()
    assert any("against the stated threshold" in i.text for i in analysis.test_ideas)


def test_threshold_stated_in_another_criterion_counts() -> None:
    analysis = analysis_of("Pages should load quickly.", "Page load time is under 2 seconds.")
    assert analysis.mandatory_clarifications == ()


def test_title_implying_an_unstated_quality_attribute_is_mandatory() -> None:
    analysis = analysis_of("Users can sign in with an email address.", title="Easy login")
    (mandatory,) = analysis.mandatory_clarifications
    assert mandatory.text == "Usability expectation"
    assert mandatory.condition_id is None
    assert "'easy'" in mandatory.reason


def test_title_attribute_already_covered_by_a_condition_is_not_repeated() -> None:
    analysis = analysis_of("Search should be fast.", title="Fast search")
    assert [a.text for a in analysis.mandatory_clarifications] == ["Performance threshold"]


def test_rules_never_supply_numbers() -> None:
    """Thresholds, limits and durations are asked for, never assumed."""
    texts = [rule.threshold_question + rule.measure for rule in QUALITY_RULES]
    for rule in DOMAIN_RULES:
        texts += [i.text for i in rule.test_ideas]
        texts += [c.question + c.topic for c in rule.clarifications]
        texts += [r.text for r in rule.risks]
    assert [t for t in texts if re.search(r"\d", t)] == []
