import logging

import pytest

from autonomous_qa_agent.error_handling import (
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_REQUEST,
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    exit_code_for,
    to_error_response,
)
from autonomous_qa_agent.models import (
    ConfigurationError,
    InvalidRequestError,
    PolicyViolationError,
    ProviderError,
    QAAgentError,
)
from autonomous_qa_agent.observability import trace_context


@pytest.mark.parametrize(
    "error_type",
    [QAAgentError, InvalidRequestError, ConfigurationError, ProviderError, PolicyViolationError],
)
def test_domain_errors_map_to_their_public_form(error_type: type[QAAgentError]) -> None:
    error = to_error_response(error_type("internal detail: host 10.0.0.5", details=["a: bad"]))
    assert error.code == error_type.code
    assert error.message == error_type.public_message
    assert error.details == ("a: bad",)
    assert "10.0.0.5" not in error.model_dump_json()


def test_internal_message_goes_to_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        to_error_response(ProviderError("socket reset at 10.0.0.5"))
    (record,) = caplog.records
    assert record.levelno == logging.WARNING
    assert record.__dict__["error_message"] == "socket reset at 10.0.0.5"
    assert record.__dict__["error_code"] == "provider_error"


def test_unexpected_errors_are_generic_and_logged_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        error = to_error_response(KeyError("api_key=sk-live-123"))
    assert error.code == INTERNAL_ERROR_CODE
    assert error.message == INTERNAL_ERROR_MESSAGE
    assert error.details == ()
    assert "sk-live" not in error.model_dump_json()
    (record,) = caplog.records
    assert record.exc_info is not None


def test_error_response_carries_the_current_trace_id() -> None:
    assert to_error_response(InvalidRequestError()).trace_id is None
    with trace_context() as trace_id:
        assert to_error_response(InvalidRequestError()).trace_id == trace_id
        assert to_error_response(RuntimeError()).trace_id == trace_id


def test_exit_codes() -> None:
    assert exit_code_for(to_error_response(InvalidRequestError())) == EXIT_INVALID_REQUEST
    assert exit_code_for(to_error_response(ProviderError())) == EXIT_INTERNAL_ERROR
    assert exit_code_for(to_error_response(RuntimeError())) == EXIT_INTERNAL_ERROR


def test_domain_errors_default_to_no_details() -> None:
    assert InvalidRequestError().details == ()
    assert InvalidRequestError(details=iter(["x"])).details == ("x",)
