import pytest

from autonomous_qa_agent.models import (
    ConfigurationError,
    InvalidRequestError,
    PolicyViolationError,
    ProviderError,
    QAAgentError,
)


@pytest.mark.parametrize(
    ("error_type", "code"),
    [
        (QAAgentError, "agent_error"),
        (InvalidRequestError, "invalid_request"),
        (ConfigurationError, "configuration_error"),
        (ProviderError, "provider_error"),
        (PolicyViolationError, "policy_violation"),
    ],
)
def test_error_codes_and_hierarchy(error_type: type[QAAgentError], code: str) -> None:
    assert error_type.code == code
    assert issubclass(error_type, QAAgentError)


def test_internal_message_is_separate_from_public_message() -> None:
    error = ProviderError("socket reset at 10.0.0.5")
    assert str(error) == "socket reset at 10.0.0.5"
    assert "10.0.0.5" not in error.public_message


def test_default_message_is_public_message() -> None:
    assert str(ConfigurationError()) == ConfigurationError.public_message
