"""Domain rules: what an experienced tester checks for a kind of feature.

A ``DomainRule`` fires for each condition that mentions its concept. It contributes:

- **test ideas** (``domain_practice``): scenarios worth testing that the requirement does not
  state. They are proposals, never reported as requirements.
- **clarifications** (``recommended``): details the requirement should state. A clarification
  is skipped when the requirement text already answers it (``answered_by``).
- **risks** and **dependencies** for the condition.

Templates never contain numbers: limits, durations and counts are always asked for, never
assumed. To support a new domain, add rules here; the engine does not change.
"""

import re
from dataclasses import dataclass

from autonomous_qa_agent.agents.requirement_rules import concepts as c
from autonomous_qa_agent.agents.requirement_rules.concepts import Concept
from autonomous_qa_agent.models.enums import ConditionKind, RiskCategory


@dataclass(frozen=True)
class IdeaTemplate:
    kind: ConditionKind
    text: str


@dataclass(frozen=True)
class ClarificationTemplate:
    topic: str  # what is missing, e.g. "OTP validity period"
    question: str
    answered_by: re.Pattern[str] | None = None  # requirement text that already states it


@dataclass(frozen=True)
class RiskTemplate:
    category: RiskCategory
    text: str


@dataclass(frozen=True)
class DomainRule:
    name: str
    domain: str
    concept: Concept
    test_ideas: tuple[IdeaTemplate, ...] = ()
    clarifications: tuple[ClarificationTemplate, ...] = ()
    risks: tuple[RiskTemplate, ...] = ()
    dependencies: tuple[str, ...] = ()


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_NEG, _BOUND, _FUNC = ConditionKind.NEGATIVE, ConditionKind.BOUNDARY, ConditionKind.FUNCTIONAL

# ------------------------------------------------------------------ authentication (banking)
OTP_VERIFICATION = DomainRule(
    name="otp_verification",
    domain="authentication",
    concept=c.OTP,
    test_ideas=(
        IdeaTemplate(_NEG, "An invalid OTP is rejected and access is not granted."),
        IdeaTemplate(_NEG, "An expired OTP is rejected and the user can request a new one."),
        IdeaTemplate(
            _FUNC, "Resending the OTP delivers a new code and the previous code stops working."
        ),
        IdeaTemplate(_NEG, "Repeated invalid OTP entries trigger the attempt limit."),
        IdeaTemplate(
            _BOUND,
            "The attempt limit is enforced exactly: the last allowed attempt still works and the "
            "next one is blocked.",
        ),
        IdeaTemplate(
            _NEG,
            "A network failure while requesting or verifying the OTP shows a recoverable error "
            "and does not leave the user half signed in.",
        ),
    ),
    clarifications=(
        ClarificationTemplate(
            "OTP validity period",
            "How long is an OTP valid before it expires?",
            _rx(r"(?:valid|expir\w*)[^.]*\d+\s*(?:s|secs?|seconds?|mins?|minutes?)\b"),
        ),
        ClarificationTemplate(
            "OTP attempt limit",
            "How many invalid OTP attempts are allowed, and what happens after the limit "
            "(lockout, cooldown, new OTP required)?",
            _rx(r"\d+\s+(?:\w+\s+)?attempts"),
        ),
        ClarificationTemplate(
            "OTP resend rules",
            "How often can an OTP be resent, and does resending invalidate the previous code?",
            _rx(r"resen\w*[^.]*\d+"),
        ),
    ),
    risks=(
        RiskTemplate(
            RiskCategory.SECURITY,
            "OTP guessing or reuse could let an attacker take over an account.",
        ),
        RiskTemplate(
            RiskCategory.INTEGRATION,
            "OTP delivery depends on an SMS provider that may be delayed or unavailable.",
        ),
    ),
    dependencies=("SMS / one-time-passcode provider",),
)

MOBILE_NUMBER_INPUT = DomainRule(
    name="mobile_number_input",
    domain="authentication",
    concept=c.MOBILE_NUMBER,
    test_ideas=(
        IdeaTemplate(
            _NEG, "A mobile number in an invalid format (letters, symbols, bad prefix) is rejected."
        ),
        IdeaTemplate(
            _BOUND,
            "Mobile numbers one digit shorter and one digit longer than the valid length are "
            "rejected.",
        ),
        IdeaTemplate(
            _NEG,
            "An unregistered mobile number is handled without revealing whether an account exists.",
        ),
    ),
    clarifications=(
        ClarificationTemplate(
            "Mobile number format",
            "Which mobile number formats are accepted (country codes, length, leading zero)?",
            _rx(r"\+\d|\d+\s*digits?|e\.164|country code"),
        ),
    ),
    risks=(
        RiskTemplate(
            RiskCategory.PRIVACY,
            "Mobile numbers are personal data and must not leak through messages or logs.",
        ),
    ),
)

AUTHENTICATION_SESSION = DomainRule(
    name="authentication_session",
    domain="authentication",
    concept=c.AUTHENTICATION,
    test_ideas=(
        IdeaTemplate(_NEG, "After the session expires, protected pages require signing in again."),
        IdeaTemplate(_NEG, "A failed sign-in does not reveal which credential was wrong."),
    ),
    clarifications=(
        ClarificationTemplate(
            "Session timeout",
            "How long may a session stay idle before it expires, and is there a maximum session "
            "lifetime?",
            _rx(r"session[^.]*\d+|\d+\s*(?:minutes?|hours?)\s+of\s+inactivity"),
        ),
    ),
    risks=(
        RiskTemplate(
            RiskCategory.SECURITY,
            "Authentication flaws can expose accounts; cover lockout, credential handling and "
            "session expiry.",
        ),
    ),
    dependencies=("Authentication / identity service",),
)

# ------------------------------------------------------------------ e-commerce
CART = DomainRule(
    name="cart",
    domain="e-commerce",
    concept=c.CART,
    test_ideas=(
        IdeaTemplate(
            _BOUND,
            "Cart quantities at the boundaries are handled: zero, one, the maximum allowed and "
            "one above it.",
        ),
        IdeaTemplate(
            _NEG, "A product that is out of stock cannot be added, or is clearly flagged."
        ),
    ),
    clarifications=(
        ClarificationTemplate(
            "Cart quantity limits",
            "What is the maximum quantity per product and per cart?",
            _rx(r"(?:max\w*|up to|at most|no more than|limit\w* to)\s+\d+"),
        ),
    ),
)

COUPON = DomainRule(
    name="coupon",
    domain="e-commerce",
    concept=c.COUPON,
    test_ideas=(
        IdeaTemplate(_NEG, "An invalid coupon code is rejected with a clear message."),
        IdeaTemplate(_NEG, "An expired coupon is rejected and the total is unchanged."),
        IdeaTemplate(_NEG, "An already-used single-use coupon is rejected on reuse."),
        IdeaTemplate(
            _BOUND,
            "A coupon with a minimum cart value is rejected just below the minimum and accepted "
            "at it.",
        ),
        IdeaTemplate(
            _FUNC, "The discount is applied to the right items and the order total is correct."
        ),
    ),
    clarifications=(
        ClarificationTemplate(
            "Coupon rules",
            "What are the coupon rules: discount type (percentage or fixed), minimum cart value, "
            "expiry, usage limit per customer, and can coupons be combined?",
        ),
    ),
    risks=(
        RiskTemplate(
            RiskCategory.FINANCIAL,
            "Wrong discount calculation or coupon reuse causes revenue loss.",
        ),
    ),
)

PAYMENT = DomainRule(
    name="payment",
    domain="e-commerce",
    concept=c.PAYMENT,
    test_ideas=(
        IdeaTemplate(
            _NEG,
            "A declined payment shows a clear message, creates no order and lets the customer "
            "retry or change method.",
        ),
        IdeaTemplate(
            _NEG,
            "Submitting payment twice (double click, retry, back button) charges the customer "
            "only once.",
        ),
        IdeaTemplate(
            _NEG,
            "A gateway timeout or network failure leaves no charge without an order and no order "
            "without a charge.",
        ),
        IdeaTemplate(_FUNC, "A successful payment creates exactly one order and a confirmation."),
    ),
    clarifications=(
        ClarificationTemplate(
            "Payment methods",
            "Which payment methods must be supported?",
            _rx(r"\b(?:visa|mastercard|amex|paypal|upi|apple pay|google pay|bank transfer)\b"),
        ),
        ClarificationTemplate(
            "Payment failure handling",
            "What should happen when a payment is declined or times out (retry, alternative "
            "method, order state)?",
        ),
    ),
    risks=(
        RiskTemplate(RiskCategory.FINANCIAL, "Incorrect or duplicate charges cause monetary loss."),
        RiskTemplate(
            RiskCategory.INTEGRATION,
            "Payment depends on an external gateway that may decline, time out or be unavailable.",
        ),
    ),
    dependencies=("Payment gateway",),
)

# ------------------------------------------------------------------ cross-domain
_GENERAL = "general"

GENERAL_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        "email_delivery",
        _GENERAL,
        c.EMAIL_SENT,
        risks=(
            RiskTemplate(
                RiskCategory.INTEGRATION,
                "Email delivery depends on an external service that may be slow or unavailable.",
            ),
        ),
        dependencies=("Email delivery service",),
    ),
    DomainRule(
        "notification",
        _GENERAL,
        c.NOTIFICATION,
        risks=(
            RiskTemplate(
                RiskCategory.INTEGRATION, "Notifications may be delayed or not delivered."
            ),
        ),
        dependencies=("Notification service",),
    ),
    DomainRule("file_transfer", _GENERAL, c.FILE_TRANSFER, dependencies=("File storage",)),
    DomainRule(
        "deletion",
        _GENERAL,
        c.DELETION,
        risks=(
            RiskTemplate(
                RiskCategory.DATA_LOSS,
                "Destructive operations may be irreversible; cover confirmation and recovery.",
            ),
        ),
    ),
    DomainRule(
        "personal_data",
        _GENERAL,
        c.PERSONAL_DATA,
        risks=(
            RiskTemplate(
                RiskCategory.PRIVACY,
                "Personal data must be handled according to data-protection rules.",
            ),
        ),
    ),
    DomainRule(
        "concurrency",
        _GENERAL,
        c.CONCURRENCY,
        risks=(
            RiskTemplate(
                RiskCategory.CONCURRENCY,
                "Simultaneous actions may cause race conditions or duplicate records.",
            ),
        ),
    ),
    DomainRule(
        "third_party",
        _GENERAL,
        c.THIRD_PARTY,
        risks=(
            RiskTemplate(
                RiskCategory.INTEGRATION,
                "Behaviour depends on an external service that may be slow or unavailable.",
            ),
        ),
        dependencies=("Third-party integration",),
    ),
)

DOMAIN_RULES: tuple[DomainRule, ...] = (
    OTP_VERIFICATION,
    MOBILE_NUMBER_INPUT,
    AUTHENTICATION_SESSION,
    CART,
    COUPON,
    PAYMENT,
    *GENERAL_RULES,
)
"""Every rule, in evaluation order."""
