"""Agent behaviour: validation, envelope and tracing, rule results, LLM enrichment.

Behaviour of the rules on real requirement examples is in ``test_requirement_examples.py``.
"""

import json
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.agents import RequirementAnalyst
from autonomous_qa_agent.agents.requirement_analyst import (
    LLM_TASK,
    LLM_UNAVAILABLE_WARNING,
    NOT_TESTABLE_WARNING,
    RequirementEnrichment,
)
from autonomous_qa_agent.llm import MockLLMProvider
from autonomous_qa_agent.models import (
    AgentRequest,
    AgentStatus,
    ConditionKind,
    InvalidRequestError,
    Necessity,
    Platform,
    Provenance,
    Requirement,
    RiskCategory,
)
from autonomous_qa_agent.observability import current_log_context, trace_context

LOGIN: dict[str, Any] = {
    "id": "REQ-1",
    "title": "User login",
    "platform": "web",
    "priority": "high",
    "acceptance_criteria": [
        "A registered user can sign in with a valid email and password",
        "Password must be at least 8 characters",
        "Email is required",
        "An invalid password shows an error message",
    ],
}


def analyst(**mock: Any) -> RequirementAnalyst:
    return RequirementAnalyst(MockLLMProvider(**mock))


def requirement(**overrides: Any) -> dict[str, Any]:
    return LOGIN | overrides


def rules(payload: dict[str, Any]) -> Any:
    return RequirementAnalyst.analyse_with_rules(Requirement.model_validate(payload))


# ------------------------------------------------------------------ validation
async def test_accepts_a_validated_requirement_or_a_mapping() -> None:
    from_mapping = await analyst().run(LOGIN)
    from_model = await analyst().run(Requirement.model_validate(LOGIN))
    assert from_mapping.output == from_model.output
    assert from_mapping.request_id != from_model.request_id
    assert from_mapping.agent == "requirement_analyst"
    assert from_mapping.output.requirement_id == "REQ-1"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({k: v for k, v in LOGIN.items() if k != "platform"}, "platform"),
        (requirement(platform="mainframe"), "platform"),
        (requirement(id="has space"), "id"),
        (requirement(title="   "), "title"),
        (requirement(acceptance_criteria=["ok", "  "]), "acceptance_criteria.1"),
        (requirement(priority="urgent"), "priority"),
        (requirement(owner="me"), "owner"),
        (requirement(acceptance_criteria=[], description=""), "<root>"),
    ],
)
async def test_rejects_invalid_requirements(payload: dict[str, Any], field: str) -> None:
    with pytest.raises(InvalidRequestError, match="invalid requirement") as info:
        await analyst().run(payload)
    assert field in str(info.value)
    assert any(d.startswith(f"{field}:") for d in info.value.details)
    assert isinstance(info.value.__cause__, ValidationError)


async def test_rejects_a_non_mapping_request() -> None:
    with pytest.raises(InvalidRequestError, match="got list"):
        await analyst().run(["not", "a", "requirement"])  # type: ignore[arg-type]


async def test_error_message_does_not_echo_input_values() -> None:
    with pytest.raises(InvalidRequestError) as info:
        await analyst().run(requirement(platform="hunter2-secret"))
    assert "hunter2" not in str(info.value)


async def test_invalid_request_never_reaches_the_llm() -> None:
    llm = MockLLMProvider()
    with pytest.raises(InvalidRequestError):
        await RequirementAnalyst(llm).run({"id": "REQ-1"})
    assert llm.requests == []


# ------------------------------------------------------------------ rule results
async def test_clear_requirement_completes_with_only_recommendations() -> None:
    response = await analyst().run(LOGIN)
    analysis = response.output

    assert response.status is AgentStatus.COMPLETED
    assert analysis.mandatory_clarifications == ()
    assert analysis.recommendations  # e.g. session timeout: useful, not blocking
    assert response.warnings == ()
    assert response.llm_enriched is False
    assert [c.id for c in analysis.conditions] == ["C-1", "C-2", "C-3", "C-4"]


async def test_conditions_are_the_stated_criteria_with_their_source() -> None:
    analysis = (await analyst().run(LOGIN)).output
    for index, condition in enumerate(analysis.conditions):
        assert condition.text == LOGIN["acceptance_criteria"][index]
        assert condition.source_text == condition.text
        assert condition.source_location == f"acceptance_criteria[{index}]"
    kinds = [c.kind for c in analysis.conditions]
    assert kinds == [ConditionKind.FUNCTIONAL] * 3 + [ConditionKind.NEGATIVE]


async def test_stated_limits_and_required_fields_become_derived_test_ideas() -> None:
    analysis = (await analyst().run(LOGIN)).output
    derived = [i for i in analysis.test_ideas if i.provenance is Provenance.DERIVED]

    assert {(i.condition_id, i.kind) for i in derived} == {
        ("C-2", ConditionKind.BOUNDARY),
        ("C-3", ConditionKind.NEGATIVE),
    }
    assert {i.kind for i in analysis.edge_cases} >= {ConditionKind.BOUNDARY}


async def test_explicit_negative_condition_gets_no_required_field_idea() -> None:
    payload = requirement(acceptance_criteria=["A required field left empty shows an error"])
    analysis = (await analyst().run(payload)).output
    assert analysis.conditions[0].kind is ConditionKind.NEGATIVE
    assert not [i for i in analysis.test_ideas if i.rule == "required_input"]


async def test_identifies_dependencies_and_risks() -> None:
    analysis = (await analyst().run(LOGIN)).output
    categories = {r.category for r in analysis.risks}

    assert analysis.dependencies == ("Authentication / identity service",)
    assert {RiskCategory.BUSINESS_IMPACT, RiskCategory.SECURITY} <= categories
    # An email address used as a credential is not an email being delivered.
    assert RiskCategory.INTEGRATION not in categories


@pytest.mark.parametrize(
    ("criterion", "dependency", "category"),
    [
        ("A confirmation email is sent after checkout", "Email delivery service", "integration"),
        ("The user pays by card at checkout", "Payment gateway", "financial"),
        ("Deleting a task removes it from the list", None, "data_loss"),
        ("Users can upload a profile picture", "File storage", "privacy"),
        ("Users are notified when a task is assigned", "Notification service", "integration"),
        ("Two users can edit a task at the same time", None, "concurrency"),
        ("Orders are synced to an external service", "Third-party integration", "integration"),
    ],
)
async def test_cross_domain_dependencies_and_risks(
    criterion: str, dependency: str | None, category: str
) -> None:
    analysis = (await analyst().run(requirement(acceptance_criteria=[criterion]))).output
    if dependency:
        assert dependency in analysis.dependencies
    assert RiskCategory(category) in {r.category for r in analysis.risks}


async def test_mobile_requirement_adds_device_risk_for_every_condition() -> None:
    analysis = (await analyst().run(requirement(platform=Platform.ANDROID))).output
    (device,) = [r for r in analysis.risks if r.category is RiskCategory.DEVICE_COMPATIBILITY]
    assert set(device.condition_ids) == analysis.condition_ids


async def test_duplicate_criteria_are_collapsed() -> None:
    criteria = ["Email is required", "email is required"]
    analysis = (await analyst().run(requirement(acceptance_criteria=criteria))).output
    assert [c.text for c in analysis.conditions] == ["Email is required"]


async def test_analysis_is_deterministic() -> None:
    first, second = await analyst().run(LOGIN), await analyst().run(LOGIN)
    assert first.model_dump(exclude={"request_id", "trace_id"}) == second.model_dump(
        exclude={"request_id", "trace_id"}
    )


async def test_requirement_without_any_behaviour_is_not_testable() -> None:
    payload = {"id": "REQ-4", "title": "Login page", "platform": "web", "description": "Redesign."}
    response = await analyst().run(payload)
    analysis = response.output

    assert not analysis.is_testable
    assert response.status is AgentStatus.NEEDS_CLARIFICATION
    assert {a.text for a in analysis.missing_criteria} == {
        "Acceptance criteria",
        "Expected behaviour",
    }
    assert all(a.necessity is Necessity.MANDATORY for a in analysis.ambiguities)
    assert analysis.risks == ()  # a risk must reference a condition; there are none
    assert NOT_TESTABLE_WARNING in response.warnings


# ------------------------------------------------------------------ envelope and tracing
async def test_envelope_ids_are_echoed_in_the_response() -> None:
    request = AgentRequest[Requirement](input=Requirement.model_validate(LOGIN))
    response = await analyst().run(request)
    assert response.request_id == request.request_id
    assert response.trace_id == request.trace_id


async def test_bare_requirement_continues_the_current_trace() -> None:
    with trace_context() as trace_id:
        response = await analyst().run(LOGIN)
    assert response.trace_id == trace_id


async def test_bare_requirement_outside_a_trace_starts_one() -> None:
    first, second = await analyst().run(LOGIN), await analyst().run(LOGIN)
    assert first.trace_id != second.trace_id


async def test_log_lines_carry_trace_and_request_ids() -> None:
    request = AgentRequest[Requirement](input=Requirement.model_validate(LOGIN))
    seen: list[dict[str, object]] = []

    class Spy(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(dict(current_log_context()))

    logger = logging.getLogger("autonomous_qa_agent")
    spy, level = Spy(), logger.level
    logger.addHandler(spy)
    logger.setLevel(logging.INFO)
    try:
        await analyst().run(request)
    finally:
        logger.removeHandler(spy)
        logger.setLevel(level)
    assert seen
    assert all(c["trace_id"] == request.trace_id for c in seen)
    assert all(c["request_id"] == str(request.request_id) for c in seen)


async def test_response_round_trips_through_json() -> None:
    response = await analyst().run(LOGIN)
    assert type(response).model_validate_json(response.model_dump_json()) == response


# ------------------------------------------------------------------ LLM enrichment
def enrichment(**fields: Any) -> str:
    return json.dumps(fields)


async def test_llm_request_carries_the_requirement_draft_and_schema() -> None:
    llm = MockLLMProvider()
    await RequirementAnalyst(llm).run(LOGIN)

    (request,) = llm.requests
    assert request.task == LLM_TASK
    assert request.response_schema == RequirementEnrichment.model_json_schema()
    prompt = json.loads(request.prompt)
    assert prompt["requirement"]["id"] == "REQ-1"
    assert [c["id"] for c in prompt["draft_analysis"]["conditions"]] == ["C-1", "C-2", "C-3", "C-4"]
    assert "Never invent" in request.system


async def test_llm_additions_are_merged_and_marked_as_suggestions() -> None:
    answer = enrichment(
        test_ideas=[
            {"condition_id": "C-1", "text": "Keyboard-only sign-in", "kind": "functional"},
            {"condition_id": "C-9", "text": "Unknown condition, dropped", "kind": "functional"},
        ],
        ambiguities=[
            {"text": "Remember me", "reason": "not stated", "question": "Is there a remember-me?",
             "kind": "missing", "condition_id": "C-1"},
            {"text": "Elsewhere", "reason": "x", "question": "Dropped?", "condition_id": "C-9"},
        ],
        risks=[
            {"text": "Keyboard users may be blocked.", "category": "other",
             "condition_ids": ["C-1", "C-9"]},
            {"text": "Only unknown ids, dropped.", "condition_ids": ["C-9"]},
        ],
        dependencies=["Audit log service", "authentication / identity service"],
        assumptions=["Single sign-on is out of scope."],
        conditions=[{"text": "LLMs cannot add explicit facts", "kind": "functional"}],
    )  # fmt: skip
    response = await analyst(responses={LLM_TASK: answer}).run(LOGIN)
    analysis = response.output

    assert response.llm_enriched is True
    assert len(analysis.conditions) == 4  # "conditions" in the answer is ignored
    (idea,) = [i for i in analysis.test_ideas if i.provenance is Provenance.LLM_SUGGESTION]
    assert (idea.condition_id, idea.rule) == ("C-1", "llm")
    assert [a.text for a in analysis.ambiguities if a.text in {"Remember me", "Elsewhere"}] == [
        "Remember me"
    ]
    llm_risks = [r for r in analysis.risks if r.provenance is Provenance.LLM_SUGGESTION]
    assert [(r.text, r.condition_ids) for r in llm_risks] == [
        ("Keyboard users may be blocked.", ("C-1",))
    ]
    assert analysis.dependencies == ("Authentication / identity service", "Audit log service")
    assert "Single sign-on is out of scope." in analysis.assumptions
    assert response.status is AgentStatus.COMPLETED  # LLM questions default to recommended


async def test_llm_mandatory_question_blocks_testing() -> None:
    answer = enrichment(
        ambiguities=[{"text": "t", "reason": "r", "question": "q?", "necessity": "mandatory"}]
    )
    response = await analyst(responses={LLM_TASK: answer}).run(LOGIN)
    assert response.status is AgentStatus.NEEDS_CLARIFICATION


async def test_llm_repeating_rule_findings_is_not_counted_as_enrichment() -> None:
    baseline = rules(LOGIN)
    idea = baseline.test_ideas[0]
    risk = baseline.risks[0]
    answer = enrichment(
        test_ideas=[{"condition_id": idea.condition_id, "text": idea.text, "kind": idea.kind}],
        ambiguities=[baseline.ambiguities[0].model_dump(mode="json")],
        risks=[{"text": risk.text, "category": risk.category, "condition_ids": risk.condition_ids}],
    )
    response = await analyst(responses={LLM_TASK: answer}).run(LOGIN)
    assert response.output == baseline
    assert response.llm_enriched is False


async def test_llm_cannot_remove_rule_results() -> None:
    answer = enrichment(test_ideas=[], risks=[], dependencies=[])
    response = await analyst(responses={LLM_TASK: answer}).run(LOGIN)
    assert response.output == rules(LOGIN)
    assert response.llm_enriched is False


@pytest.mark.parametrize(
    "mock",
    [
        {"failures": frozenset({LLM_TASK})},
        {"responses": {LLM_TASK: "I think the requirement is fine."}},
        {
            "responses": {
                LLM_TASK: enrichment(
                    test_ideas=[{"condition_id": "C-1", "text": "x", "kind": "made-up"}]
                )
            }
        },
    ],
    ids=["provider-error", "not-json", "schema-mismatch"],
)
async def test_llm_problems_fall_back_to_rules(mock: dict[str, Any]) -> None:
    response = await analyst(**mock).run(LOGIN)

    assert response.output == rules(LOGIN)
    assert response.llm_enriched is False
    assert response.warnings == (LLM_UNAVAILABLE_WARNING,)
    assert response.status is AgentStatus.COMPLETED
