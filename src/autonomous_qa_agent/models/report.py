"""Run summary and final report."""

from collections import Counter
from collections.abc import Iterable
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, NonNegativeInt, model_validator

from autonomous_qa_agent.models.analysis import FailureAnalysis, HealingRecommendation
from autonomous_qa_agent.models.approval import ApprovalDecision
from autonomous_qa_agent.models.common import ContractModel, Identifier, find_duplicates
from autonomous_qa_agent.models.enums import RunStatus, TestStatus
from autonomous_qa_agent.models.results import TestResult


def latest_attempts(results: Iterable[TestResult]) -> dict[str, TestResult]:
    """The highest-numbered attempt for each scenario (earlier attempts are history)."""
    latest: dict[str, TestResult] = {}
    for result in results:
        current = latest.get(result.scenario_id)
        if current is None or result.attempt > current.attempt:
            latest[result.scenario_id] = result
    return latest


class RunSummary(ContractModel):
    """Counts per scenario, using each scenario's latest attempt."""

    total: NonNegativeInt
    passed: NonNegativeInt
    failed: NonNegativeInt
    errored: NonNegativeInt
    skipped: NonNegativeInt
    blocked: NonNegativeInt

    @model_validator(mode="after")
    def _counts_add_up(self) -> Self:
        if self.passed + self.failed + self.errored + self.skipped + self.blocked != self.total:
            raise ValueError("status counts must add up to total")
        return self

    @classmethod
    def from_results(cls, results: Iterable[TestResult]) -> Self:
        counts = Counter(r.status for r in latest_attempts(results).values())
        return cls(
            total=sum(counts.values()),
            passed=counts[TestStatus.PASSED],
            failed=counts[TestStatus.FAILED],
            errored=counts[TestStatus.ERROR],
            skipped=counts[TestStatus.SKIPPED],
            blocked=counts[TestStatus.BLOCKED],
        )

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class RunReport(ContractModel):
    """Final, self-consistent record of a run."""

    run_id: UUID
    status: RunStatus
    requirement_id: Identifier
    environment_name: Identifier
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    summary: RunSummary
    results: tuple[TestResult, ...] = ()
    failures: tuple[FailureAnalysis, ...] = ()
    recommendations: tuple[HealingRecommendation, ...] = ()
    approvals: tuple[ApprovalDecision, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status.is_terminal != (self.finished_at is not None):
            raise ValueError("finished_at must be set exactly when the run status is terminal")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if duplicated := find_duplicates(f"{r.scenario_id}#{r.attempt}" for r in self.results):
            raise ValueError(f"duplicate result attempts: {duplicated}")
        if self.summary != RunSummary.from_results(self.results):
            raise ValueError("summary does not match results")
        return self
