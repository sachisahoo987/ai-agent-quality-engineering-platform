from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    EvidenceKind,
    EvidenceRef,
    ExecutionError,
    StepResult,
    TestResult,
    TestStatus,
)

Factory = Callable[..., Any]


def test_step_duration_is_derived(make_step_result: Factory) -> None:
    assert make_step_result().duration_ms == 250


def test_step_timestamps_must_be_aware_and_ordered(make_step_result: Factory, t0: datetime) -> None:
    with pytest.raises(ValidationError):
        make_step_result(started_at=t0.replace(tzinfo=None))
    with pytest.raises(ValidationError, match="must not precede"):
        make_step_result(finished_at=t0 - timedelta(seconds=1))


@pytest.mark.parametrize("status", [TestStatus.FAILED, TestStatus.ERROR])
def test_failed_step_requires_error(make_step_result: Factory, status: TestStatus) -> None:
    with pytest.raises(ValidationError, match="must include an error"):
        make_step_result(status=status, error=None)


@pytest.mark.parametrize("status", [TestStatus.PASSED, TestStatus.SKIPPED, TestStatus.BLOCKED])
def test_non_failed_step_rejects_error(make_step_result: Factory, status: TestStatus) -> None:
    with pytest.raises(ValidationError, match="only a failed"):
        make_step_result(status=status, error=ExecutionError(type="X", message="y"))


def test_step_accepts_evidence(make_step_result: Factory) -> None:
    ref = EvidenceRef(kind=EvidenceKind.SCREENSHOT, uri="artifacts/run/1.png")
    assert make_step_result(evidence=(ref,)).evidence == (ref,)


def test_passed_test(make_test_result: Factory) -> None:
    result: TestResult = make_test_result()
    assert result.first_failure is None
    assert result.duration_ms == 250


def test_failed_test_exposes_first_failure(
    make_test_result: Factory, make_step_result: Factory
) -> None:
    ok: StepResult = make_step_result(step_id="s1")
    bad: StepResult = make_step_result(step_id="s2", status=TestStatus.FAILED)
    skipped: StepResult = make_step_result(step_id="s3", status=TestStatus.SKIPPED)
    result: TestResult = make_test_result(status=TestStatus.FAILED, steps=(ok, bad, skipped))
    assert result.first_failure == bad
    assert result.duration_ms == 750


def test_passed_test_needs_all_steps_passed(
    make_test_result: Factory, make_step_result: Factory
) -> None:
    with pytest.raises(ValidationError, match="a passed test"):
        make_test_result(steps=())
    with pytest.raises(ValidationError, match="a passed test"):
        make_test_result(steps=(make_step_result(status=TestStatus.SKIPPED),))


def test_failed_step_forces_failed_status(
    make_test_result: Factory, make_step_result: Factory
) -> None:
    with pytest.raises(ValidationError, match="must be failed or errored"):
        make_test_result(
            status=TestStatus.SKIPPED, steps=(make_step_result(status=TestStatus.FAILED),)
        )


def test_blocked_test_may_have_no_steps(make_test_result: Factory) -> None:
    assert make_test_result(status=TestStatus.BLOCKED).steps == ()


def test_test_result_rejects_duplicate_steps_and_bad_attempt(
    make_test_result: Factory, make_step_result: Factory
) -> None:
    with pytest.raises(ValidationError, match="duplicate step ids"):
        make_test_result(steps=(make_step_result(), make_step_result()))
    with pytest.raises(ValidationError):
        make_test_result(attempt=0)


def test_execution_error_details_must_be_json(make_step_result: Factory) -> None:
    with pytest.raises(ValidationError):
        ExecutionError(type="X", message="y", details={"obj": object()})
    err = ExecutionError(type="X", message="y", details={"selector": "#a", "retries": [1, 2]})
    result: StepResult = make_step_result(status=TestStatus.ERROR, error=err)
    assert StepResult.model_validate_json(result.model_dump_json()) == result
