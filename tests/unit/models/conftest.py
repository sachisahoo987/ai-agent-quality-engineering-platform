"""Factories for valid contracts; each test overrides only the fields it is about."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from autonomous_qa_agent.models import (
    ActionRisk,
    ActionType,
    DriverKind,
    ExecutableStep,
    ExecutionError,
    ExecutionPlan,
    Locator,
    LocatorStrategy,
    PlannedTest,
    Platform,
    StepResult,
    TargetEnvironment,
    Technique,
    TestResult,
    TestScenario,
    TestStatus,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
RUN_ID = UUID("00000000-0000-4000-8000-000000000001")

Factory = Callable[..., Any]


@pytest.fixture
def t0() -> datetime:
    return T0


@pytest.fixture
def run_id() -> UUID:
    return RUN_ID


@pytest.fixture
def locator() -> Locator:
    return Locator(strategy=LocatorStrategy.TEST_ID, value="save-button")


@pytest.fixture
def web_env() -> TargetEnvironment:
    return TargetEnvironment(
        name="local-web", platform=Platform.WEB, base_url="http://localhost:3000", disposable=True
    )


@pytest.fixture
def make_scenario() -> Factory:
    def make(**overrides: Any) -> TestScenario:
        data: dict[str, Any] = {
            "id": "SC-001",
            "requirement_id": "REQ-1",
            "title": "Create a task",
            "technique": Technique.POSITIVE,
            "steps": ("Open the task page", "Create a task"),
            "expected_results": ("The task is listed",),
            "traces_to": ("C-1",),
        }
        return TestScenario(**(data | overrides))

    return make


@pytest.fixture
def make_step(locator: Locator) -> Factory:
    def make(**overrides: Any) -> ExecutableStep:
        data: dict[str, Any] = {
            "id": "step-1",
            "action": ActionType.CLICK,
            "risk": ActionRisk.READ_ONLY,
            "locator": locator,
        }
        return ExecutableStep(**(data | overrides))

    return make


@pytest.fixture
def make_planned_test(make_step: Factory) -> Factory:
    def make(**overrides: Any) -> PlannedTest:
        data: dict[str, Any] = {
            "scenario_id": "SC-001",
            "driver": DriverKind.PLAYWRIGHT,
            "steps": (make_step(),),
        }
        return PlannedTest(**(data | overrides))

    return make


@pytest.fixture
def make_plan(web_env: TargetEnvironment, make_planned_test: Factory) -> Factory:
    def make(**overrides: Any) -> ExecutionPlan:
        data: dict[str, Any] = {
            "run_id": RUN_ID,
            "environment": web_env,
            "tests": (make_planned_test(),),
        }
        return ExecutionPlan(**(data | overrides))

    return make


@pytest.fixture
def make_step_result() -> Factory:
    def make(**overrides: Any) -> StepResult:
        status = overrides.get("status", TestStatus.PASSED)
        data: dict[str, Any] = {
            "step_id": "step-1",
            "status": status,
            "started_at": T0,
            "finished_at": T0 + timedelta(milliseconds=250),
            "error": (
                ExecutionError(type="ElementNotFound", message="no element")
                if status.is_failure
                else None
            ),
        }
        return StepResult(**(data | overrides))

    return make


@pytest.fixture
def make_test_result(make_step_result: Factory) -> Factory:
    def make(**overrides: Any) -> TestResult:
        status = overrides.get("status", TestStatus.PASSED)
        step_status = status if status in (TestStatus.PASSED, TestStatus.FAILED) else None
        data: dict[str, Any] = {
            "scenario_id": "SC-001",
            "status": status,
            "steps": (make_step_result(status=step_status),) if step_status else (),
        }
        return TestResult(**(data | overrides))

    return make
