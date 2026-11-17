"""Non-functional requirement classification.

Each ``QualityRule`` says how to recognise one quality attribute, what a *measurable* statement
of it looks like, and which question to ask when the threshold is missing. A statement that
signals an attribute but has no measurable threshold gets a mandatory clarification. The rules
never supply a threshold themselves, so questions and test ideas contain no numbers.
"""

import re
from dataclasses import dataclass

from autonomous_qa_agent.agents.requirement_rules.concepts import Concept
from autonomous_qa_agent.models.enums import QualityAttribute


@dataclass(frozen=True)
class QualityRule:
    attribute: QualityAttribute
    indicators: Concept  # wording that expresses the attribute
    measurable: re.Pattern[str]  # what a stated, verifiable threshold looks like
    measure: str  # what a test of this attribute measures
    threshold_question: str


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_DURATION = r"\d+(?:\.\d+)?\s*(?:ms|milliseconds?|s|secs?|seconds?|min|minutes?)\b"
_PERCENT = r"\d+(?:\.\d+)?\s*%"

QUALITY_RULES: tuple[QualityRule, ...] = (
    QualityRule(
        QualityAttribute.PERFORMANCE,
        Concept(
            "performance",
            terms=(
                "fast",
                "faster",
                "quick",
                "quickly",
                "slow",
                "responsive",
                "instant",
                "instantly",
                "efficient",
                "efficiently",
                "performance",
                "response time",
                "load time",
                "latency",
                "speed",
            ),
        ),
        _rx(rf"{_DURATION}|\bp\d{{2,3}}\b|\bpercentile\b"),
        "the response or load time",
        "What is the maximum acceptable response or load time, and under which conditions "
        "(network, device, data volume, percentile) is it measured?",
    ),
    QualityRule(
        QualityAttribute.SCALABILITY,
        Concept(
            "scalability",
            terms=(
                "scalable",
                "scalability",
                "peak load",
                "high traffic",
                "throughput",
                "concurrent users",
                "simultaneous users",
                "growing number",
            ),
        ),
        _rx(
            r"\d[\d,]*\s*(?:\w+\s+)?(?:users|requests|transactions|orders|sessions)\b"
            r"|\bper (?:second|minute)"
        ),
        "the load the system sustains",
        "What load must be supported (concurrent users, requests or transactions per second), "
        "and what response time is acceptable at that load?",
    ),
    QualityRule(
        QualityAttribute.RELIABILITY,
        Concept(
            "reliability",
            terms=(
                "reliable",
                "reliably",
                "reliability",
                "fault tolerant",
                "fault-tolerant",
                "recover from failure",
                "disaster recovery",
                "resilient",
                "without data loss",
                "error rate",
            ),
        ),
        _rx(rf"{_PERCENT}|\bmtbf\b|\brpo\b|\brto\b|{_DURATION}"),
        "the error rate and recovery behaviour",
        "What failure rate is acceptable, and how quickly and to what state must the system "
        "recover (RTO / RPO)?",
    ),
    QualityRule(
        QualityAttribute.AVAILABILITY,
        Concept(
            "availability",
            terms=(
                "availability",
                "highly available",
                "always available",
                "uptime",
                "downtime",
                "24/7",
                "always on",
            ),
        ),
        _rx(rf"{_PERCENT}|\bsla\b|\d+\s*(?:hours?|minutes?)\s+(?:of\s+)?downtime"),
        "the availability",
        "What availability is required (for example as an uptime percentage or SLA), over what "
        "period, and are maintenance windows excluded?",
    ),
    QualityRule(
        QualityAttribute.SECURITY,
        Concept(
            "security",
            terms=(
                "secure",
                "securely",
                "security",
                "encrypt",
                "encrypted",
                "encryption",
                "protected",
                "vulnerability",
                "tamper",
            ),
        ),
        _rx(r"\b(?:tls|aes|rsa|owasp|pci[- ]?dss|iso ?27001|sha-?\d+|\d+-bit|oauth|mfa|2fa)\b"),
        "compliance with the agreed security controls",
        "Which security controls or standards apply (for example encryption in transit and at "
        "rest, OWASP ASVS level, PCI DSS)?",
    ),
    QualityRule(
        QualityAttribute.USABILITY,
        Concept(
            "usability",
            terms=(
                "user-friendly",
                "user friendly",
                "easy",
                "easily",
                "intuitive",
                "usable",
                "usability",
                "simple",
                "accessible",
                "accessibility",
                "clean",
                "modern",
                "nice",
            ),
        ),
        _rx(rf"\bwcag\b|\d+\s*(?:clicks?|steps?|taps?)\b|{_PERCENT}|\bsus\b"),
        "task success and accessibility",
        "Which observable usability or accessibility measure applies (for example task "
        "completion without help, number of steps, a WCAG level)?",
    ),
)


def quality_attributes(text: str) -> tuple[QualityAttribute, ...]:
    """The quality attributes ``text`` expresses, in rule order."""
    return tuple(rule.attribute for rule in QUALITY_RULES if rule.indicators.found_in(text))


def rule_for(attribute: QualityAttribute) -> QualityRule:
    return next(rule for rule in QUALITY_RULES if rule.attribute is attribute)
