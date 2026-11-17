"""Find the statements a requirement makes and split compound ones into testable parts.

A *statement* is one acceptance criterion or, when there are none, one description sentence
that describes behaviour. A *compound* statement coordinates several actions under one subject
("A customer should be able to add products to the cart, apply a discount coupon and complete
payment"); each action becomes its own clause, prefixed with the shared subject so it reads as a
complete statement.

Splitting is deliberately conservative: a statement is only split when *every* part starts with
an action verb, so noun lists ("mobile number and OTP", "email and password") stay together.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from autonomous_qa_agent.models.requirement import Requirement

_BEHAVIOUR = re.compile(
    r"\b(?:must|shall|should|can|will|allows?|enables?|lets|displays?|shows?|appears?|loads?)\b"
    # observable outcomes in the passive voice: "the task is shown", "a receipt is sent"
    r"|\b(?:is|are|gets?|becomes?)\s+(?:\w+ed|shown|seen|sent|kept|hidden|written)\b",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")

# "<subject> should be able to <actions>" / "<subject> can <actions>" / "users must <actions>"
_MODAL_PREFIX = re.compile(
    r"^(?P<prefix>.*?\b(?:must|shall|should|can|will|may)(?:\s+(?:be able|be allowed) to)?)"
    r"\s+(?P<actions>.+?)\s*(?P<end>[.!?]?)$",
    re.IGNORECASE,
)
_COORDINATION = re.compile(r"\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or|as well as)\s+", re.I)

# Verbs that start a user action in requirements. A closed, linguistic list (what a part must
# start with to count as a separate action), not domain vocabulary.
_ACTION_VERBS: frozenset[str] = frozenset(
    (
        "access", "add", "apply", "approve", "book", "browse", "buy", "cancel", "change",
        "check", "checkout", "choose", "close", "compare", "complete", "configure", "confirm",
        "create", "delete", "download", "edit", "enter", "export", "filter", "find", "generate",
        "import", "invite", "join", "leave", "log", "manage", "modify", "open", "order", "pay",
        "place", "print", "purchase", "receive", "redeem", "register", "reject", "remove",
        "rename", "reorder", "request", "reset", "retry", "review", "save", "schedule", "search",
        "see", "select", "send", "set", "share", "sign", "sort", "submit", "subscribe", "track",
        "transfer", "unsubscribe", "update", "upload", "use", "verify", "view", "withdraw",
    )
)  # fmt: skip


@dataclass(frozen=True)
class Statement:
    text: str  # verbatim, apart from list markers
    location: str  # "description" or "acceptance_criteria[i]"


def statements(requirement: Requirement) -> list[Statement]:
    """Acceptance criteria, or the description's behaviour sentences when there are none."""
    if requirement.acceptance_criteria:
        found = (
            Statement(text, f"acceptance_criteria[{i}]")
            for i, text in enumerate(requirement.acceptance_criteria)
        )
    else:
        sentences = (
            _BULLET.sub("", s).strip() for s in _SENTENCE_BREAK.split(requirement.description)
        )
        found = (Statement(s, "description") for s in sentences if s and _BEHAVIOUR.search(s))
    return _unique_statements(found)


def decompose(text: str) -> list[str]:
    """Split a compound statement into one clause per action; otherwise return ``[text]``."""
    match = _MODAL_PREFIX.match(text)
    if not match:
        return [text]
    parts = [p for p in _COORDINATION.split(match.group("actions")) if p]
    if len(parts) < 2 or not all(_is_verb(p.split()[0]) for p in parts):
        return [text]
    *leading, last = parts
    _, *shared_object = last.split()
    if not shared_object:  # "add and remove": nothing to act on
        return [text]
    # A bare verb shares the last action's object: "approve or reject the request".
    actions = [p if len(p.split()) > 1 else f"{p} {' '.join(shared_object)}" for p in leading]
    prefix, end = match.group("prefix"), match.group("end")
    return [f"{prefix} {action}{end}" for action in [*actions, last]]


def _is_verb(word: str) -> bool:
    return word.lower() in _ACTION_VERBS


def _unique_statements(found: Iterable[Statement]) -> list[Statement]:
    seen: set[str] = set()
    result: list[Statement] = []
    for statement in found:
        key = statement.text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(statement)
    return result
