"""Requirement analyst: turns a requirement into a structured, traceable QA analysis.

Rules decide first (see ``requirement_rules``). The LLM is then asked only for *additions* that
reference existing conditions: test ideas, clarifications, risks, assumptions and dependencies.
It cannot add conditions, because explicit facts come only from the requirement text, and it
cannot remove or rewrite what the rules found. Proposals that reference unknown conditions are
dropped. If the provider fails or answers with something unusable, the rule-based analysis is
returned with a warning.
"""

import json
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from autonomous_qa_agent.agents.requirement_rules import Draft, analyse
from autonomous_qa_agent.models.agent import AgentRequest, AgentResponse
from autonomous_qa_agent.models.common import Identifier, NonEmptyStr, new_trace_id
from autonomous_qa_agent.models.enums import (
    AgentStatus,
    AmbiguityKind,
    ConditionKind,
    Necessity,
    Provenance,
    RiskCategory,
)
from autonomous_qa_agent.models.errors import InvalidRequestError, ProviderError
from autonomous_qa_agent.models.requirement import Ambiguity, Requirement, RequirementAnalysis
from autonomous_qa_agent.observability.logging import (
    current_trace_id,
    get_logger,
    log_context,
    trace_context,
)
from autonomous_qa_agent.ports.llm import LLMProvider, LLMRequest
from autonomous_qa_agent.ports.structured import generate_structured

AGENT_NAME = "requirement_analyst"
LLM_TASK = "requirement_analysis"
LLM_UNAVAILABLE_WARNING = "LLM enrichment was unavailable; the analysis is rule-based only."
NOT_TESTABLE_WARNING = "No testable conditions were found; the requirement needs detail."

_log = get_logger(__name__)


# ------------------------------------------------------------------ LLM contract
class _Proposal(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class _ProposedTestIdea(_Proposal):
    condition_id: Identifier
    text: NonEmptyStr = Field(max_length=1_000)
    kind: ConditionKind


class _ProposedAmbiguity(_Proposal):
    text: NonEmptyStr = Field(max_length=1_000)
    reason: NonEmptyStr = Field(max_length=1_000)
    question: NonEmptyStr = Field(max_length=1_000)
    kind: AmbiguityKind = AmbiguityKind.AMBIGUOUS
    necessity: Necessity = Necessity.RECOMMENDED
    condition_id: Identifier | None = None


class _ProposedRisk(_Proposal):
    text: NonEmptyStr = Field(max_length=1_000)
    category: RiskCategory = RiskCategory.OTHER
    condition_ids: list[Identifier] = Field(min_length=1, max_length=50)


class RequirementEnrichment(_Proposal):
    """What the LLM may add to the rule-based analysis. Every list holds additions only."""

    test_ideas: list[_ProposedTestIdea] = Field(default_factory=list, max_length=50)
    ambiguities: list[_ProposedAmbiguity] = Field(default_factory=list, max_length=50)
    risks: list[_ProposedRisk] = Field(default_factory=list, max_length=20)
    assumptions: list[NonEmptyStr] = Field(default_factory=list, max_length=20)
    dependencies: list[NonEmptyStr] = Field(default_factory=list, max_length=20)


_SYSTEM_PROMPT = (
    "You are a senior QA analyst. You receive a software requirement and a draft analysis "
    "produced by deterministic rules. Return ONLY a JSON object matching the given schema that "
    "lists ADDITIONS to the draft: test ideas, clarifying questions, risks, assumptions and "
    "external dependencies. Every test idea and risk must reference the id of an existing "
    "condition. Never invent requirements, thresholds, limits or numbers that the requirement "
    "does not state; ask a clarifying question instead. Do not repeat items already in the "
    "draft. Return empty lists when there is nothing to add."
)


# ------------------------------------------------------------------ agent
class RequirementAnalyst:
    """Analyse a requirement into conditions, test ideas, clarifications, risks and more."""

    name = AGENT_NAME

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def run(
        self, request: AgentRequest[Requirement] | Requirement | Mapping[str, object]
    ) -> AgentResponse[RequirementAnalysis]:
        """Validate ``request``, analyse it and return the analysis in an ``AgentResponse``.

        ``request`` is an ``AgentRequest`` envelope, or a bare requirement (model or mapping),
        which is wrapped in a new envelope that continues the current trace, if any.
        Raises ``InvalidRequestError`` when the requirement is invalid.
        """
        envelope = self.validate(request)
        requirement = envelope.input
        with (
            trace_context(envelope.trace_id),
            log_context(
                agent=self.name,
                request_id=str(envelope.request_id),
                requirement_id=requirement.id,
            ),
        ):
            draft = analyse(requirement)
            warnings: list[str] = []
            enriched = False
            try:
                enrichment = await self._ask_llm(requirement, draft.freeze())
            except ProviderError as exc:
                _log.warning("llm enrichment failed", extra={"error_code": exc.code})
                warnings.append(LLM_UNAVAILABLE_WARNING)
            else:
                enriched = _merge(draft, enrichment)

            analysis = draft.freeze()
            if not analysis.is_testable:
                warnings.append(NOT_TESTABLE_WARNING)
            status = (
                AgentStatus.NEEDS_CLARIFICATION
                if analysis.needs_clarification
                else AgentStatus.COMPLETED
            )
            _log.info(
                "requirement analysed",
                extra={
                    "status": status.value,
                    "conditions": len(analysis.conditions),
                    "test_ideas": len(analysis.test_ideas),
                    "mandatory_clarifications": len(analysis.mandatory_clarifications),
                    "recommendations": len(analysis.recommendations),
                    "llm_enriched": enriched,
                },
            )
            return AgentResponse[RequirementAnalysis](
                request_id=envelope.request_id,
                trace_id=envelope.trace_id,
                agent=self.name,
                status=status,
                output=analysis,
                llm_enriched=enriched,
                warnings=tuple(warnings),
            )

    @staticmethod
    def validate(
        request: AgentRequest[Requirement] | Requirement | Mapping[str, object],
    ) -> AgentRequest[Requirement]:
        """Return ``request`` as a validated envelope or raise ``InvalidRequestError``."""
        if isinstance(request, AgentRequest):
            return request
        if isinstance(request, Requirement):
            requirement = request
        elif isinstance(request, Mapping):
            try:
                requirement = Requirement.model_validate(request)
            except ValidationError as exc:
                # Field locations and messages only: input values may be sensitive.
                problems = [
                    f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
                ]
                raise InvalidRequestError(
                    f"invalid requirement: {'; '.join(problems)}", details=problems
                ) from exc
        else:
            problem = f"expected a requirement object, got {type(request).__name__}"
            raise InvalidRequestError(problem, details=[problem])
        return AgentRequest[Requirement](
            input=requirement, trace_id=current_trace_id() or new_trace_id()
        )

    @staticmethod
    def analyse_with_rules(requirement: Requirement) -> RequirementAnalysis:
        """The deterministic analysis, without any LLM involvement."""
        return analyse(requirement).freeze()

    async def _ask_llm(
        self, requirement: Requirement, draft: RequirementAnalysis
    ) -> RequirementEnrichment:
        prompt = json.dumps(
            {
                "requirement": requirement.model_dump(mode="json"),
                "draft_analysis": draft.model_dump(mode="json"),
            },
            indent=2,
        )
        request = LLMRequest(task=LLM_TASK, system=_SYSTEM_PROMPT, prompt=prompt)
        return await generate_structured(self._llm, request, RequirementEnrichment)


def _merge(draft: Draft, enrichment: RequirementEnrichment) -> bool:
    """Add the LLM's proposals to ``draft``; drop any that reference unknown conditions.

    Returns whether anything new was added.
    """
    known = set(draft.condition_ids)
    added = False
    for idea in enrichment.test_ideas:
        if idea.condition_id in known:
            added |= draft.add_test_idea(
                idea.condition_id, idea.text, idea.kind, Provenance.LLM_SUGGESTION, "llm"
            )
    for proposed in enrichment.ambiguities:
        if proposed.condition_id is None or proposed.condition_id in known:
            added |= draft.add_ambiguity(Ambiguity(**proposed.model_dump()))
    for risk in enrichment.risks:
        linked = [cid for cid in risk.condition_ids if cid in known]
        added |= draft.add_risk(risk.text, risk.category, linked, Provenance.LLM_SUGGESTION)
    for target, values in (
        (draft.assumptions, enrichment.assumptions),
        (draft.dependencies, enrichment.dependencies),
    ):
        for value in values:
            added |= draft.add_text(target, value)
    return added
