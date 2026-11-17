"""Deterministic requirement analysis: applies the statement, quality and domain rules.

The engine holds no vocabulary of its own. It turns statements into conditions, then asks each
rule module what it has to say about each condition, and records every finding against the
condition it came from.
"""

from dataclasses import dataclass, field

from autonomous_qa_agent.agents.requirement_rules import concepts as c
from autonomous_qa_agent.agents.requirement_rules.concepts import Concept
from autonomous_qa_agent.agents.requirement_rules.domains import DOMAIN_RULES, DomainRule
from autonomous_qa_agent.agents.requirement_rules.quality import (
    quality_attributes,
    rule_for,
)
from autonomous_qa_agent.agents.requirement_rules.statements import decompose, statements
from autonomous_qa_agent.models.enums import (
    AmbiguityKind,
    ConditionKind,
    Necessity,
    Platform,
    Priority,
    Provenance,
    QualityAttribute,
    RiskCategory,
)
from autonomous_qa_agent.models.requirement import (
    Ambiguity,
    Requirement,
    RequirementAnalysis,
    Risk,
    TestableCondition,
    TestIdea,
)

_HIGH_PRIORITIES = frozenset({Priority.CRITICAL, Priority.HIGH})

# Wording that cannot be verified as written, and the question that resolves it.
_UNVERIFIABLE_WORDING: tuple[tuple[Concept, str, str], ...] = (
    (c.UNSPECIFIED_QUANTITY, "is an unspecified quantity", "What exact number or range is meant?"),
    (
        c.OPEN_ENDED,
        "leaves the behaviour open-ended",
        "What is the complete, definitive behaviour?",
    ),
    (
        c.QUALITY_JUDGEMENT,
        "is a quality judgement, not a verifiable outcome",
        "What specific, verifiable outcome is expected?",
    ),
)

DOMAIN_IDEAS_ASSUMPTION = (
    "Domain test ideas reflect common practice for this kind of feature. They are not stated "
    "requirements; confirm them with the requirement owner."
)
DECOMPOSITION_ASSUMPTION = (
    "Compound statements were split into one condition per action; each condition keeps the "
    "original statement as its source."
)


def _quoted(terms: list[str]) -> str:
    return ", ".join(f"'{t}'" for t in terms)


@dataclass
class Draft:
    """Mutable accumulator, frozen into a ``RequirementAnalysis`` at the end."""

    requirement_id: str
    conditions: list[TestableCondition] = field(default_factory=list)
    test_ideas: list[TestIdea] = field(default_factory=list)
    ambiguities: list[Ambiguity] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    _risks: dict[tuple[RiskCategory, str], tuple[str, Provenance, list[str]]] = field(
        default_factory=dict
    )

    @property
    def condition_ids(self) -> list[str]:
        return [cond.id for cond in self.conditions]

    def add_test_idea(
        self,
        condition_id: str,
        text: str,
        kind: ConditionKind,
        provenance: Provenance,
        rule: str | None = None,
    ) -> bool:
        existing = [i for i in self.test_ideas if i.condition_id == condition_id]
        if any(i.text.casefold() == text.casefold() for i in existing):
            return False
        self.test_ideas.append(
            TestIdea(
                id=f"{condition_id}:T-{len(existing) + 1}",
                condition_id=condition_id,
                text=text,
                kind=kind,
                provenance=provenance,
                rule=rule,
            )
        )
        return True

    def add_ambiguity(self, ambiguity: Ambiguity) -> bool:
        key = (ambiguity.text.casefold(), ambiguity.question.casefold())
        if any((a.text.casefold(), a.question.casefold()) == key for a in self.ambiguities):
            return False
        self.ambiguities.append(ambiguity)
        return True

    def add_risk(
        self,
        text: str,
        category: RiskCategory,
        condition_ids: list[str],
        provenance: Provenance,
    ) -> bool:
        """Record a risk; the same risk raised by several conditions is merged."""
        if not condition_ids:
            return False
        key = (category, text.casefold())
        if key not in self._risks:
            self._risks[key] = (text, provenance, list(condition_ids))
            return True
        linked = self._risks[key][2]
        new = [cid for cid in condition_ids if cid not in linked]
        linked.extend(new)
        return bool(new)

    @staticmethod
    def add_text(target: list[str], text: str) -> bool:
        if any(t.casefold() == text.casefold() for t in target):
            return False
        target.append(text)
        return True

    def freeze(self) -> RequirementAnalysis:
        return RequirementAnalysis(
            requirement_id=self.requirement_id,
            conditions=tuple(self.conditions),
            test_ideas=tuple(self.test_ideas),
            ambiguities=tuple(self.ambiguities),
            assumptions=tuple(self.assumptions),
            dependencies=tuple(self.dependencies),
            risks=tuple(
                Risk(text=text, category=category, condition_ids=tuple(ids), provenance=prov)
                for (category, _), (text, prov, ids) in self._risks.items()
            ),
        )


# ------------------------------------------------------------------ entry point
def analyse(requirement: Requirement) -> Draft:
    """Run every rule against ``requirement``."""
    draft = Draft(requirement_id=requirement.id)
    _extract_conditions(draft, requirement)
    full_text = "\n".join(
        (requirement.title, requirement.description, *requirement.acceptance_criteria)
    )
    has_stated_negative = any(cond.kind is ConditionKind.NEGATIVE for cond in draft.conditions)

    for condition in draft.conditions:
        _derive_from_stated_text(draft, condition)
        _check_quality_thresholds(draft, condition)
        _check_wording(draft, condition)
        feature_rules = _apply_domain_rules(draft, condition, full_text)
        if not feature_rules:
            _check_input_handling(draft, condition, has_stated_negative)

    _check_title(draft, requirement)
    _check_requirement_level(draft, requirement)
    _requirement_risks(draft, requirement)
    _record_assumptions(draft, requirement)
    return draft


# ------------------------------------------------------------------ conditions
def _extract_conditions(draft: Draft, requirement: Requirement) -> None:
    for n, statement in enumerate(statements(requirement), start=1):
        clauses = decompose(statement.text)
        for k, clause in enumerate(clauses, start=1):
            attributes = quality_attributes(clause)
            if attributes:
                kind = ConditionKind.NON_FUNCTIONAL
            elif c.NEGATIVE_OUTCOME.found_in(clause):
                kind = ConditionKind.NEGATIVE
            else:
                kind = ConditionKind.FUNCTIONAL
            draft.conditions.append(
                TestableCondition(
                    id=f"C-{n}" if len(clauses) == 1 else f"C-{n}.{k}",
                    text=clause,
                    kind=kind,
                    source_text=statement.text,
                    source_location=statement.location,
                    quality_attributes=attributes,
                )
            )


def _derive_from_stated_text(draft: Draft, condition: TestableCondition) -> None:
    """Test ideas that follow directly from what the condition states."""
    if c.STATED_NUMERIC_LIMIT.found_in(condition.text):
        draft.add_test_idea(
            condition.id,
            f"Values at, just below and just above the stated limit are handled: {condition.text}",
            ConditionKind.BOUNDARY,
            Provenance.DERIVED,
            "stated_limit",
        )
    if c.REQUIRED_INPUT.found_in(condition.text) and condition.kind is not ConditionKind.NEGATIVE:
        draft.add_test_idea(
            condition.id,
            f"Omitting the required input is rejected with a clear message: {condition.text}",
            ConditionKind.NEGATIVE,
            Provenance.DERIVED,
            "required_input",
        )


def _check_quality_thresholds(draft: Draft, condition: TestableCondition) -> None:
    for attribute in condition.quality_attributes:
        rule = rule_for(attribute)
        if _threshold_stated(draft, attribute):
            draft.add_test_idea(
                condition.id,
                f"Verify {rule.measure} against the stated threshold: {condition.text}",
                ConditionKind.NON_FUNCTIONAL,
                Provenance.DERIVED,
                f"quality_{attribute.value}",
            )
            continue
        terms = _quoted(rule.indicators.matches(condition.text))
        draft.add_ambiguity(
            Ambiguity(
                text=f"{attribute.value.capitalize()} threshold",
                reason=f"{terms} states a {attribute.value} expectation without a measurable "
                "threshold.",
                question=rule.threshold_question,
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.MANDATORY,
                condition_id=condition.id,
            )
        )
        draft.add_test_idea(
            condition.id,
            f"Measure {rule.measure} and compare it with the agreed threshold; the condition "
            "cannot pass or fail until the threshold is defined.",
            ConditionKind.NON_FUNCTIONAL,
            Provenance.DERIVED,
            f"quality_{attribute.value}",
        )


def _threshold_stated(draft: Draft, attribute: QualityAttribute) -> bool:
    """A measurable threshold for ``attribute`` appears in any statement expressing it."""
    rule = rule_for(attribute)
    return any(
        attribute in cond.quality_attributes and rule.measurable.search(cond.source_text)
        for cond in draft.conditions
    )


def _check_wording(draft: Draft, condition: TestableCondition) -> None:
    for concept, reason, question in _UNVERIFIABLE_WORDING:
        if terms := concept.matches(condition.text):
            draft.add_ambiguity(
                Ambiguity(
                    text=condition.text,
                    reason=f"{_quoted(terms)} {reason}.",
                    question=question,
                    necessity=Necessity.MANDATORY,
                    condition_id=condition.id,
                )
            )


def _apply_domain_rules(
    draft: Draft, condition: TestableCondition, full_text: str
) -> list[DomainRule]:
    """Apply every rule whose concept the condition mentions; return the feature rules that fired
    (rules that bring their own test ideas and therefore their own error cases)."""
    fired: list[DomainRule] = []
    for rule in DOMAIN_RULES:
        if not rule.concept.found_in(condition.text):
            continue
        if rule.test_ideas:
            fired.append(rule)
        for idea in rule.test_ideas:
            draft.add_test_idea(
                condition.id, idea.text, idea.kind, Provenance.DOMAIN_PRACTICE, rule.name
            )
        for clarification in rule.clarifications:
            if clarification.answered_by and clarification.answered_by.search(full_text):
                continue
            draft.add_ambiguity(
                Ambiguity(
                    text=clarification.topic,
                    reason=f"The requirement does not state the {clarification.topic[0].lower()}"
                    f"{clarification.topic[1:]}.",
                    question=clarification.question,
                    kind=AmbiguityKind.MISSING,
                    necessity=Necessity.RECOMMENDED,
                    condition_id=condition.id,
                )
            )
        for risk in rule.risks:
            draft.add_risk(risk.text, risk.category, [condition.id], Provenance.DOMAIN_PRACTICE)
        for dependency in rule.dependencies:
            draft.add_text(draft.dependencies, dependency)
    return fired


def _check_input_handling(
    draft: Draft, condition: TestableCondition, has_stated_negative: bool
) -> None:
    """Generic input checks, only for conditions about user input that no feature rule covers."""
    if not c.USER_INPUT.found_in(condition.text):
        return
    if not has_stated_negative:
        draft.add_ambiguity(
            Ambiguity(
                text="Invalid-input handling",
                reason="The condition involves user input, but no criterion says what happens "
                "when the input is invalid.",
                question="How should the system respond to invalid input (message, field state, "
                "whether entered data is kept)?",
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.RECOMMENDED,
                condition_id=condition.id,
            )
        )
    if not c.STATED_NUMERIC_LIMIT.found_in(condition.text):
        draft.add_ambiguity(
            Ambiguity(
                text="Input limits",
                reason="The condition involves user input, but no length, range or format limit "
                "is stated.",
                question="What are the allowed lengths, ranges and formats for each input?",
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.RECOMMENDED,
                condition_id=condition.id,
            )
        )


# ------------------------------------------------------------------ requirement level
def _check_title(draft: Draft, requirement: Requirement) -> None:
    """The title can imply expectations the body never states."""
    title = requirement.title
    if any(cond.text.casefold() == title.casefold() for cond in draft.conditions):
        return
    stated = {attr for cond in draft.conditions for attr in cond.quality_attributes}
    for attribute in quality_attributes(title):
        if attribute in stated:
            continue
        rule = rule_for(attribute)
        draft.add_ambiguity(
            Ambiguity(
                text=f"{attribute.value.capitalize()} expectation",
                reason=f"The title implies a {attribute.value} expectation "
                f"({_quoted(rule.indicators.matches(title))}) that no statement makes "
                "measurable.",
                question=rule.threshold_question,
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.MANDATORY,
            )
        )
    asked = {a.question for a in draft.ambiguities}
    for concept, reason, question in _UNVERIFIABLE_WORDING:
        if question not in asked and (terms := concept.matches(title)):
            draft.add_ambiguity(
                Ambiguity(text=title, reason=f"{_quoted(terms)} {reason}.", question=question)
            )


def _check_requirement_level(draft: Draft, requirement: Requirement) -> None:
    if not requirement.acceptance_criteria:
        draft.add_ambiguity(
            Ambiguity(
                text="Acceptance criteria",
                reason="No acceptance criteria are given"
                + (
                    "; the conditions were taken from the description." if draft.conditions else "."
                ),
                question="Which acceptance criteria define done for this requirement?",
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.RECOMMENDED if draft.conditions else Necessity.MANDATORY,
            )
        )
    if not draft.conditions:
        draft.add_ambiguity(
            Ambiguity(
                text="Expected behaviour",
                reason="No statement describes what the system must do.",
                question="What should the system do, for whom, and with what observable result?",
                kind=AmbiguityKind.MISSING,
                necessity=Necessity.MANDATORY,
            )
        )


def _requirement_risks(draft: Draft, requirement: Requirement) -> None:
    every = draft.condition_ids
    if requirement.priority in _HIGH_PRIORITIES:
        draft.add_risk(
            f"{requirement.priority.value.capitalize()} priority: a defect here is costly.",
            RiskCategory.BUSINESS_IMPACT,
            every,
            Provenance.DERIVED,
        )
    if requirement.platform is not Platform.WEB:
        draft.add_risk(
            "Behaviour may differ across OS versions, devices and screen sizes.",
            RiskCategory.DEVICE_COMPATIBILITY,
            every,
            Provenance.DERIVED,
        )
    mandatory = [a for a in draft.ambiguities if a.necessity is Necessity.MANDATORY]
    if mandatory:
        affected = (
            every
            if any(a.condition_id is None for a in mandatory)
            else [cid for cid in every if any(a.condition_id == cid for a in mandatory)]
        )
        draft.add_risk(
            "Tests may verify the wrong behaviour until the mandatory questions are answered.",
            RiskCategory.UNCLEAR_REQUIREMENT,
            affected,
            Provenance.DERIVED,
        )


def _record_assumptions(draft: Draft, requirement: Requirement) -> None:
    if requirement.acceptance_criteria:
        draft.add_text(draft.assumptions, "Conditions follow the acceptance criteria as written.")
    elif draft.conditions:
        draft.add_text(
            draft.assumptions,
            "No acceptance criteria were given; conditions were taken from the description.",
        )
    if any(cond.text != cond.source_text for cond in draft.conditions):
        draft.add_text(draft.assumptions, DECOMPOSITION_ASSUMPTION)
    if any(i.provenance is Provenance.DOMAIN_PRACTICE for i in draft.test_ideas):
        draft.add_text(draft.assumptions, DOMAIN_IDEAS_ASSUMPTION)
