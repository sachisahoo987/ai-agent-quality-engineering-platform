"""Domain errors.

Each error carries a stable machine-readable ``code`` and a ``public_message`` that is safe to
show to API callers. The constructor message is for logs only and may contain internal detail.
"""

from typing import ClassVar


class QAAgentError(Exception):
    """Base class for expected, reportable agent errors."""

    code: ClassVar[str] = "agent_error"
    public_message: ClassVar[str] = "The agent could not complete the request."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)


class InvalidRequestError(QAAgentError):
    code: ClassVar[str] = "invalid_request"
    public_message: ClassVar[str] = "The request is invalid."


class ConfigurationError(QAAgentError):
    code: ClassVar[str] = "configuration_error"
    public_message: ClassVar[str] = "The agent configuration is invalid."


class ProviderError(QAAgentError):
    code: ClassVar[str] = "provider_error"
    public_message: ClassVar[str] = "The language model provider failed."


class PolicyViolationError(QAAgentError):
    code: ClassVar[str] = "policy_violation"
    public_message: ClassVar[str] = "The action was blocked by the safety policy."
