"""Requirement input and its analysis.

An analysis keeps four kinds of finding apart:

- **Explicit facts**: ``conditions``. Only what the requirement states, with its original text.
- **Inferred scenarios**: ``test_ideas``. Derived from a condition, never presented as stated.
- **Assumptions**: ``assumptions``. What the analysis took for granted.
- **Clarifications**: ``ambiguities``. Questions for the requirement owner, either
  ``mandatory`` (blocks testing) or ``recommended``.

Test ideas, clarifications and risks reference the condition they came from, and the model
rejects references to conditions that do not exist.
"""

from typing import Self

from pydantic import Field, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    find_duplicates,
)
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


class Requirement(ContractModel):
    """A product requirement or user story to be tested."""

    id: Identifier
    title: NonEmptyStr = Field(max_length=200)
    description: str = Field(default="", max_length=10_000)
    acceptance_criteria: tuple[NonEmptyStr, ...] = Field(default=(), max_length=100)
    platform: Platform
    priority: Priority = Priority.MEDIUM
    source: str | None = Field(default=None, max_length=500)  # e.g. ticket URL or file path

    @model_validator(mode="after")
    def _has_testable_content(self) -> Self:
        if not self.description and not self.acceptance_criteria:
            raise ValueError("a requirement needs a description or acceptance criteria")
        return self


class TestableCondition(ContractModel):
    """One verifiable statement the requirement makes (an explicit fact).

    ``text`` is the statement or, for a compound statement, one of its parts. ``source_text``
    is the original statement verbatim and ``source_location`` says where it is
    (``description`` or ``acceptance_criteria[2]``).
    """

    __test__ = False

    id: Identifier
    text: NonEmptyStr
    kind: ConditionKind
    source_text: NonEmptyStr
    source_location: NonEmptyStr = Field(max_length=100)
    quality_attributes: tuple[QualityAttribute, ...] = ()

    @model_validator(mode="after")
    def _attributes_match_kind(self) -> Self:
        non_functional = self.kind is ConditionKind.NON_FUNCTIONAL
        if non_functional and not self.quality_attributes:
            raise ValueError("a non_functional condition needs at least one quality attribute")
        if not non_functional and self.quality_attributes:
            raise ValueError("quality attributes are only valid on non_functional conditions")
        return self


class TestIdea(ContractModel):
    """An inferred scenario worth testing. Not stated by the requirement; see ``provenance``."""

    __test__ = False

    id: Identifier
    condition_id: Identifier
    text: NonEmptyStr
    kind: ConditionKind
    provenance: Provenance
    rule: str | None = Field(default=None, max_length=100)  # the rule that produced it


class Ambiguity(ContractModel):
    """A clarification: requirement text that cannot be tested as written, or that is absent.

    ``kind`` separates vague criteria (``AMBIGUOUS``: ``text`` quotes the requirement) from
    criteria that are absent (``MISSING``: ``text`` names what is missing). ``condition_id`` is
    the condition it concerns, or ``None`` when it concerns the requirement as a whole.
    """

    text: NonEmptyStr
    reason: NonEmptyStr
    question: NonEmptyStr
    kind: AmbiguityKind = AmbiguityKind.AMBIGUOUS
    necessity: Necessity = Necessity.MANDATORY
    condition_id: Identifier | None = None


class Risk(ContractModel):
    """A quality risk and the conditions it affects."""

    text: NonEmptyStr
    category: RiskCategory
    condition_ids: tuple[Identifier, ...] = Field(min_length=1)
    provenance: Provenance


_EDGE_CASE_KINDS = frozenset({ConditionKind.BOUNDARY, ConditionKind.NEGATIVE})


class RequirementAnalysis(ContractModel):
    """Output of the requirement analyst."""

    requirement_id: Identifier
    conditions: tuple[TestableCondition, ...] = ()
    test_ideas: tuple[TestIdea, ...] = ()
    ambiguities: tuple[Ambiguity, ...] = ()
    assumptions: tuple[NonEmptyStr, ...] = ()
    dependencies: tuple[NonEmptyStr, ...] = ()  # external systems the behaviour relies on
    risks: tuple[Risk, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if duplicated := find_duplicates(c.id for c in self.conditions):
            raise ValueError(f"duplicate condition ids: {duplicated}")
        if duplicated := find_duplicates(i.id for i in self.test_ideas):
            raise ValueError(f"duplicate test idea ids: {duplicated}")
        known = self.condition_ids
        referenced = (
            {i.condition_id for i in self.test_ideas}
            | {a.condition_id for a in self.ambiguities if a.condition_id is not None}
            | {cid for r in self.risks for cid in r.condition_ids}
        )
        if unknown := sorted(referenced - known):
            raise ValueError(f"references to unknown condition ids: {unknown}")
        return self

    @property
    def is_testable(self) -> bool:
        return bool(self.conditions)

    @property
    def condition_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.conditions)

    @property
    def functional_conditions(self) -> tuple[TestableCondition, ...]:
        return tuple(c for c in self.conditions if c.kind is ConditionKind.FUNCTIONAL)

    @property
    def non_functional_conditions(self) -> tuple[TestableCondition, ...]:
        return tuple(c for c in self.conditions if c.kind is ConditionKind.NON_FUNCTIONAL)

    @property
    def edge_cases(self) -> tuple[TestIdea, ...]:
        """Boundary and negative test ideas."""
        return tuple(i for i in self.test_ideas if i.kind in _EDGE_CASE_KINDS)

    @property
    def missing_criteria(self) -> tuple[Ambiguity, ...]:
        return tuple(a for a in self.ambiguities if a.kind is AmbiguityKind.MISSING)

    @property
    def mandatory_clarifications(self) -> tuple[Ambiguity, ...]:
        return tuple(a for a in self.ambiguities if a.necessity is Necessity.MANDATORY)

    @property
    def recommendations(self) -> tuple[Ambiguity, ...]:
        return tuple(a for a in self.ambiguities if a.necessity is Necessity.RECOMMENDED)

    @property
    def needs_clarification(self) -> bool:
        """True when testing is blocked: a mandatory question is open or nothing is testable."""
        return bool(self.mandatory_clarifications) or not self.is_testable

    def test_ideas_for(self, condition_id: str) -> tuple[TestIdea, ...]:
        return tuple(i for i in self.test_ideas if i.condition_id == condition_id)
