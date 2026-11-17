"""Domain data contracts. Depends on Pydantic only: no I/O, no frameworks."""

from autonomous_qa_agent.models.analysis import FailureAnalysis, HealingRecommendation
from autonomous_qa_agent.models.approval import ApprovalDecision, ApprovalItem, ApprovalRequest
from autonomous_qa_agent.models.common import (
    Confidence,
    ContractModel,
    Identifier,
    NonEmptyStr,
    SecretRef,
)
from autonomous_qa_agent.models.enums import (
    ActionRisk,
    ActionType,
    ApprovalKind,
    ConditionKind,
    DriverKind,
    EvidenceKind,
    FailureCategory,
    HealingAction,
    LocatorStrategy,
    Platform,
    Priority,
    RunStatus,
    Technique,
    TestStatus,
    highest_risk,
)
from autonomous_qa_agent.models.errors import (
    ConfigurationError,
    InvalidRequestError,
    PolicyViolationError,
    ProviderError,
    QAAgentError,
)
from autonomous_qa_agent.models.execution import (
    DeviceProfile,
    ExecutableStep,
    ExecutionPlan,
    Locator,
    PlannedTest,
    TargetEnvironment,
)
from autonomous_qa_agent.models.report import RunReport, RunSummary, latest_attempts
from autonomous_qa_agent.models.requirement import (
    Ambiguity,
    Requirement,
    RequirementAnalysis,
    TestableCondition,
)
from autonomous_qa_agent.models.results import (
    EvidenceRef,
    ExecutionError,
    StepResult,
    TestResult,
)
from autonomous_qa_agent.models.scenario import TestScenario

__all__ = [
    "ActionRisk",
    "ActionType",
    "Ambiguity",
    "ApprovalDecision",
    "ApprovalItem",
    "ApprovalKind",
    "ApprovalRequest",
    "ConditionKind",
    "Confidence",
    "ConfigurationError",
    "ContractModel",
    "DeviceProfile",
    "DriverKind",
    "EvidenceKind",
    "EvidenceRef",
    "ExecutableStep",
    "ExecutionError",
    "ExecutionPlan",
    "FailureAnalysis",
    "FailureCategory",
    "HealingAction",
    "HealingRecommendation",
    "Identifier",
    "InvalidRequestError",
    "Locator",
    "LocatorStrategy",
    "NonEmptyStr",
    "PlannedTest",
    "Platform",
    "PolicyViolationError",
    "Priority",
    "ProviderError",
    "QAAgentError",
    "Requirement",
    "RequirementAnalysis",
    "RunReport",
    "RunStatus",
    "RunSummary",
    "SecretRef",
    "StepResult",
    "TargetEnvironment",
    "Technique",
    "TestResult",
    "TestScenario",
    "TestStatus",
    "TestableCondition",
    "highest_risk",
    "latest_attempts",
]
