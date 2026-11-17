"""Unit tests for domain models."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ExecutionStatus,
    ScenarioPriority,
)
from autonomous_qa_agent.models.execution import TestExecutionResult as ExecutionResult
from autonomous_qa_agent.models.scenario import TestScenario as Scenario


def test_agent_request_generates_identifiers_and_normalizes_task() -> None:
    request = AgentRequest(task="  Test task  ")

    assert request.task == "Test task"
    assert request.request_id != request.correlation_id
    assert request.context == {}


@pytest.mark.parametrize("task", ["", "  ", "\n\t"])
def test_agent_request_rejects_blank_task(task: str) -> None:
    with pytest.raises(ValidationError):
        AgentRequest(task=task)


def test_agent_request_is_immutable_and_rejects_extra_fields() -> None:
    request = AgentRequest(task="Test task")
    with pytest.raises(ValidationError):
        request.task = "Changed"
    with pytest.raises(ValidationError):
        AgentRequest(task="Test", unexpected="value")


def test_agent_request_normalizes_trace_id_and_rejects_blank_trace_id() -> None:
    request = AgentRequest(task="Test task", trace_id=" trace-123 ")

    assert request.trace_id == "trace-123"
    with pytest.raises(ValidationError):
        AgentRequest(task="Test task", trace_id="  ")


def test_completed_agent_response_requires_output_without_errors() -> None:
    response = AgentResponse(
        request_id=uuid4(),
        correlation_id=uuid4(),
        status=AgentStatus.COMPLETED,
        output="Analysis complete",
    )

    assert response.output == "Analysis complete"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": AgentStatus.COMPLETED},
        {"status": AgentStatus.FAILED, "error_code": "provider_error"},
        {
            "status": AgentStatus.FAILED,
            "error_code": "provider_error",
            "error_message": "Failed",
            "output": "x",
        },
        {"status": AgentStatus.RUNNING},
    ],
)
def test_agent_response_rejects_inconsistent_status_payload(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AgentResponse(
            request_id=uuid4(),
            correlation_id=uuid4(),
            **payload,
        )


def test_test_scenario_normalizes_fields_and_defaults_priority() -> None:
    scenario = Scenario(
        title="  Create task ",
        description="  User creates a task  ",
        steps=[" Open project ", " Submit task "],
        expected_result=" Task is visible ",
    )

    assert scenario.title == "Create task"
    assert scenario.steps == ("Open project", "Submit task")
    assert scenario.priority is ScenarioPriority.MEDIUM


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": " "},
        {"description": ""},
        {"steps": []},
        {"steps": [" "]},
        {"expected_result": "\n"},
        {"priority": "urgent"},
    ],
)
def test_test_scenario_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "title": "Create task",
        "description": "User creates a task",
        "steps": ["Submit task"],
        "expected_result": "Task is visible",
    }
    values.update(overrides)

    with pytest.raises(ValidationError):
        Scenario(**values)


def test_execution_result_accepts_timezone_aware_chronological_timestamps() -> None:
    started_at = datetime.now(UTC)
    result = ExecutionResult(
        scenario_id=uuid4(),
        status=ExecutionStatus.PASSED,
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=1),
        duration_seconds=1,
    )

    assert result.status is ExecutionStatus.PASSED


@pytest.mark.parametrize(
    ("started_at", "finished_at", "duration"),
    [
        (datetime.now(), datetime.now(), 0),
        (datetime.now(UTC), datetime.now(UTC) - timedelta(seconds=1), 0),
        (datetime.now(UTC), datetime.now(UTC), -1),
    ],
)
def test_execution_result_rejects_invalid_timing(
    started_at: datetime,
    finished_at: datetime,
    duration: float,
) -> None:
    with pytest.raises(ValidationError):
        ExecutionResult(
            scenario_id=uuid4(),
            status=ExecutionStatus.FAILED,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
        )
