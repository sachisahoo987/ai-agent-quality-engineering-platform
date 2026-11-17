"""Enumerations shared by all data contracts, and the action-capability tables."""

from collections.abc import Iterable
from enum import StrEnum


class DriverKind(StrEnum):
    """Automation backend that executes a planned test."""

    PLAYWRIGHT = "playwright"
    APPIUM = "appium"


class Platform(StrEnum):
    """Platform of the application under test."""

    WEB = "web"
    ANDROID = "android"
    IOS = "ios"

    @property
    def is_mobile(self) -> bool:
        return self is not Platform.WEB

    @property
    def driver(self) -> DriverKind:
        """The automation backend that drives this platform."""
        return DriverKind.APPIUM if self.is_mobile else DriverKind.PLAYWRIGHT


class Priority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConditionKind(StrEnum):
    """Kind of testable condition extracted from a requirement."""

    FUNCTIONAL = "functional"
    BOUNDARY = "boundary"
    NEGATIVE = "negative"
    NON_FUNCTIONAL = "non_functional"


class AmbiguityKind(StrEnum):
    """Why part of a requirement cannot be tested as written."""

    AMBIGUOUS = "ambiguous"  # present but vague or open to interpretation
    MISSING = "missing"  # an acceptance criterion the requirement should state but does not


class Necessity(StrEnum):
    """Whether a clarification blocks testing."""

    MANDATORY = "mandatory"  # the condition cannot be verified until this is answered
    RECOMMENDED = "recommended"  # testing can start; answering it improves the tests


class Provenance(StrEnum):
    """Where an analysis finding comes from. Explicit facts are the conditions themselves."""

    DERIVED = "derived"  # follows directly from the stated text (a stated limit's boundaries)
    DOMAIN_PRACTICE = "domain_practice"  # common practice for this kind of feature; not stated
    LLM_SUGGESTION = "llm_suggestion"  # proposed by the language model


class QualityAttribute(StrEnum):
    """Category of a non-functional requirement."""

    PERFORMANCE = "performance"
    SCALABILITY = "scalability"
    RELIABILITY = "reliability"
    AVAILABILITY = "availability"
    SECURITY = "security"
    USABILITY = "usability"


class RiskCategory(StrEnum):
    BUSINESS_IMPACT = "business_impact"
    SECURITY = "security"
    FINANCIAL = "financial"
    DATA_LOSS = "data_loss"
    PRIVACY = "privacy"
    CONCURRENCY = "concurrency"
    INTEGRATION = "integration"
    DEVICE_COMPATIBILITY = "device_compatibility"
    UNCLEAR_REQUIREMENT = "unclear_requirement"
    OTHER = "other"


class AgentStatus(StrEnum):
    """Outcome of one agent invocation."""

    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"  # output is usable but has open questions


class Technique(StrEnum):
    """Test design technique that produced a scenario."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY_VALUE = "boundary_value"
    EQUIVALENCE_PARTITION = "equivalence_partition"
    STATE_TRANSITION = "state_transition"
    ERROR_GUESSING = "error_guessing"


class ActionType(StrEnum):
    """Closed vocabulary of executable actions. Only these can ever reach a tool."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    PRESS_KEY = "press_key"
    TAP = "tap"
    SWIPE = "swipe"
    ASSERT_VISIBLE = "assert_visible"
    ASSERT_TEXT = "assert_text"
    ASSERT_URL = "assert_url"
    SCREENSHOT = "screenshot"
    SNAPSHOT = "snapshot"


class LocatorStrategy(StrEnum):
    """How an element is located. Ordered roughly from most to least resilient."""

    ROLE = "role"
    TEST_ID = "test_id"
    LABEL = "label"
    ACCESSIBILITY_ID = "accessibility_id"
    TEXT = "text"
    CSS = "css"
    XPATH = "xpath"


class ActionRisk(StrEnum):
    """Side-effect level of an action; drives the safety policy and approvals."""

    READ_ONLY = "read_only"
    STATE_CHANGING = "state_changing"
    DESTRUCTIVE = "destructive"

    @property
    def rank(self) -> int:
        """Numeric severity for comparisons (string ordering of members is meaningless)."""
        return _RISK_RANK[self]


_RISK_RANK: dict[ActionRisk, int] = {
    ActionRisk.READ_ONLY: 0,
    ActionRisk.STATE_CHANGING: 1,
    ActionRisk.DESTRUCTIVE: 2,
}


def highest_risk(risks: Iterable[ActionRisk]) -> ActionRisk:
    """The most severe risk in ``risks``; ``READ_ONLY`` when empty."""
    return max(risks, key=lambda risk: risk.rank, default=ActionRisk.READ_ONLY)


class TestStatus(StrEnum):
    """Outcome of a step or a test."""

    __test__ = False  # not a pytest test class

    PASSED = "passed"
    FAILED = "failed"  # the application did not behave as expected
    ERROR = "error"  # the test could not run correctly (tooling, environment)
    SKIPPED = "skipped"
    BLOCKED = "blocked"  # refused by safety policy or a rejected approval

    @property
    def is_failure(self) -> bool:
        return self in (TestStatus.FAILED, TestStatus.ERROR)


class EvidenceKind(StrEnum):
    SCREENSHOT = "screenshot"
    DOM = "dom"
    ACCESSIBILITY_TREE = "accessibility_tree"
    CONSOLE_LOG = "console_log"
    NETWORK_LOG = "network_log"


class FailureCategory(StrEnum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    TIMING = "timing"
    ASSERTION_MISMATCH = "assertion_mismatch"
    ENVIRONMENT = "environment"
    TEST_DATA = "test_data"
    PRODUCT_DEFECT_SUSPECTED = "product_defect_suspected"
    UNKNOWN = "unknown"


class HealingAction(StrEnum):
    UPDATE_LOCATOR = "update_locator"
    ADD_EXPLICIT_WAIT = "add_explicit_wait"
    UPDATE_TEST_DATA = "update_test_data"
    QUARANTINE = "quarantine"
    FILE_DEFECT = "file_defect"


class ApprovalKind(StrEnum):
    PLAN = "plan"
    HEALING = "healing"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_RUN_STATUSES


_TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.REJECTED, RunStatus.CANCELLED}
)

# ------------------------------------------------------------------ action capability tables
LOCATOR_REQUIRED_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.CLICK,
        ActionType.FILL,
        ActionType.SELECT,
        ActionType.TAP,
        ActionType.ASSERT_VISIBLE,
        ActionType.ASSERT_TEXT,
    }
)
"""Actions that operate on an element and therefore need a locator."""

VALUE_REQUIRED_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.NAVIGATE,  # URL or path
        ActionType.FILL,  # text (or a secret_ref)
        ActionType.SELECT,  # option
        ActionType.PRESS_KEY,  # key name
        ActionType.SWIPE,  # direction
    }
)
"""Actions that need an input value."""

EXPECTED_REQUIRED_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.ASSERT_TEXT, ActionType.ASSERT_URL}
)
"""Assertions that compare against an expected value."""

MOBILE_ONLY_ACTIONS: frozenset[ActionType] = frozenset({ActionType.TAP, ActionType.SWIPE})
"""Gestures only a mobile driver can perform."""

SECRET_CAPABLE_ACTIONS: frozenset[ActionType] = frozenset({ActionType.FILL})
"""Actions whose input may come from a secret reference."""
