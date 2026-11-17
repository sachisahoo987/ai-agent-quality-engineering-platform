from uuid import UUID

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    AgentRequest,
    AgentResponse,
    AgentStatus,
    ErrorResponse,
    Platform,
    Requirement,
    RequirementAnalysis,
    TestScenario,
    new_trace_id,
)

TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
REQUEST_ID = UUID("00000000-0000-4000-8000-000000000001")
REQUIREMENT = Requirement(id="REQ-1", title="Login", description="d", platform=Platform.WEB)


def response(**overrides: object) -> AgentResponse[RequirementAnalysis]:
    data: dict[str, object] = {
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "agent": "requirement_analyst",
        "status": AgentStatus.COMPLETED,
        "output": RequirementAnalysis(requirement_id="REQ-1"),
    }
    return AgentResponse[RequirementAnalysis].model_validate(data | overrides)


# ------------------------------------------------------------------ AgentRequest
def test_agent_request_generates_unique_ids() -> None:
    first = AgentRequest[Requirement](input=REQUIREMENT)
    second = AgentRequest[Requirement](input=REQUIREMENT)
    assert first.request_id != second.request_id
    assert first.trace_id != second.trace_id
    assert len(first.trace_id) == 32


def test_agent_request_accepts_explicit_ids_and_validates_input() -> None:
    request = AgentRequest[Requirement].model_validate(
        {
            "request_id": str(REQUEST_ID),
            "trace_id": TRACE_ID,
            "input": {"id": "REQ-1", "title": "t", "description": "d", "platform": "web"},
        }
    )
    assert request.request_id == REQUEST_ID
    assert request.input == Requirement(id="REQ-1", title="t", description="d", platform="web")


@pytest.mark.parametrize(
    "fields",
    [
        {"trace_id": "not-a-trace"},
        {"trace_id": TRACE_ID.upper()},
        {"request_id": "123"},
        {"input": {"id": "REQ-1"}},
        {"unknown": 1},
    ],
)
def test_agent_request_rejects_invalid_fields(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentRequest[Requirement].model_validate({"input": REQUIREMENT} | fields)


def test_new_trace_id_is_lowercase_hex() -> None:
    trace_id = new_trace_id()
    assert len(trace_id) == 32
    assert int(trace_id, 16) >= 0
    assert trace_id == trace_id.lower()


# ------------------------------------------------------------------ AgentResponse
def test_agent_response_wraps_typed_output() -> None:
    result = response()
    assert result.llm_enriched is False
    assert result.warnings == ()
    assert AgentResponse[RequirementAnalysis].model_validate_json(result.model_dump_json()) == (
        result
    )


def test_agent_response_validates_the_output_type() -> None:
    with pytest.raises(ValidationError):
        AgentResponse[TestScenario].model_validate(
            {
                "request_id": REQUEST_ID,
                "trace_id": TRACE_ID,
                "agent": "a",
                "status": AgentStatus.COMPLETED,
                "output": RequirementAnalysis(requirement_id="REQ-1"),
            }
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"agent": " "},
        {"status": "done"},
        {"trace_id": "x"},
        {"request_id": None},
        {"warnings": ("",)},
        {"extra": 1},
    ],
)
def test_agent_response_rejects_invalid_fields(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        response(**fields)


def test_agent_response_is_immutable() -> None:
    result = response()
    with pytest.raises(ValidationError):
        result.status = AgentStatus.NEEDS_CLARIFICATION  # type: ignore[misc]


@pytest.mark.parametrize("status", list(AgentStatus))
def test_agent_status_values_are_stable(status: AgentStatus) -> None:
    assert status.value in {"completed", "needs_clarification"}


# ------------------------------------------------------------------ ErrorResponse
def test_error_response_defaults() -> None:
    error = ErrorResponse(code="invalid_request", message="The request is invalid.")
    assert error.details == ()
    assert error.trace_id is None


@pytest.mark.parametrize(
    "fields", [{"code": "has space"}, {"message": " "}, {"trace_id": "short"}, {"details": ("",)}]
)
def test_error_response_rejects_invalid_fields(fields: dict[str, object]) -> None:
    data: dict[str, object] = {"code": "invalid_request", "message": "m"} | fields
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate(data)
