from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    RunReport,
    RunStatus,
    RunSummary,
    TestResult,
    TestStatus,
    latest_attempts,
)

Factory = Callable[..., Any]


def test_latest_attempt_wins(make_test_result: Factory) -> None:
    first: TestResult = make_test_result(status=TestStatus.FAILED, attempt=1)
    retry: TestResult = make_test_result(status=TestStatus.PASSED, attempt=2)
    assert latest_attempts([retry, first]) == {"SC-001": retry}


def test_summary_counts_latest_attempts(make_test_result: Factory) -> None:
    results = [
        make_test_result(scenario_id="A", status=TestStatus.FAILED, attempt=1),
        make_test_result(scenario_id="A", status=TestStatus.PASSED, attempt=2),
        make_test_result(scenario_id="B", status=TestStatus.FAILED),
        make_test_result(scenario_id="C", status=TestStatus.BLOCKED),
        make_test_result(scenario_id="D", status=TestStatus.SKIPPED),
        make_test_result(scenario_id="E", status=TestStatus.ERROR),
    ]
    summary = RunSummary.from_results(results)
    assert summary == RunSummary(total=5, passed=1, failed=1, errored=1, skipped=1, blocked=1)
    assert summary.pass_rate == pytest.approx(0.2)


def test_empty_summary() -> None:
    summary = RunSummary.from_results([])
    assert summary.total == 0
    assert summary.pass_rate == 0.0


def test_summary_counts_must_add_up() -> None:
    with pytest.raises(ValidationError, match="add up"):
        RunSummary(total=2, passed=1, failed=0, errored=0, skipped=0, blocked=0)


@pytest.fixture
def report_factory(make_test_result: Factory, t0: datetime, run_id: UUID) -> Factory:
    def make(**overrides: Any) -> RunReport:
        results = overrides.pop("results", (make_test_result(),))
        data: dict[str, Any] = {
            "run_id": run_id,
            "status": RunStatus.COMPLETED,
            "requirement_id": "REQ-1",
            "environment_name": "local-web",
            "started_at": t0,
            "finished_at": t0 + timedelta(minutes=2),
            "summary": RunSummary.from_results(results),
            "results": results,
        }
        return RunReport(**(data | overrides))

    return make


def test_report_round_trip(report_factory: Factory) -> None:
    report: RunReport = report_factory()
    assert RunReport.model_validate_json(report.model_dump_json()) == report


def test_report_summary_must_match_results(report_factory: Factory) -> None:
    wrong = RunSummary(total=1, passed=0, failed=1, errored=0, skipped=0, blocked=0)
    with pytest.raises(ValidationError, match="summary does not match"):
        report_factory(summary=wrong)


def test_report_finished_at_tracks_terminal_status(report_factory: Factory, t0: datetime) -> None:
    with pytest.raises(ValidationError, match="exactly when"):
        report_factory(finished_at=None)
    with pytest.raises(ValidationError, match="exactly when"):
        report_factory(status=RunStatus.AWAITING_APPROVAL)
    assert report_factory(status=RunStatus.RUNNING, finished_at=None).finished_at is None
    with pytest.raises(ValidationError, match="must not precede"):
        report_factory(finished_at=t0 - timedelta(seconds=1))


def test_report_rejects_duplicate_attempts(
    report_factory: Factory, make_test_result: Factory
) -> None:
    with pytest.raises(ValidationError, match="duplicate result attempts"):
        report_factory(results=(make_test_result(), make_test_result()))
