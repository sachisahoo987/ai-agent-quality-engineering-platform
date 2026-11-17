"""Named concepts: the vocabulary that every rule is written against.

A ``Concept`` groups the words for one idea (``OTP``: "otp", "one-time password",
"verification code"). Rules reference concepts instead of repeating word lists, so the word
list for an idea lives in exactly one place and is reused by every rule that needs it.

Terms match whole words, case-insensitively, including the common inflections of the last word
("delete" matches "deletes", "deleted", "deleting"; "coupon" matches "coupons").
"""

import re
from dataclasses import dataclass, field


def _inflected(term: str) -> str:
    words = term.lower().split()
    *head, last = words
    stem = re.escape(last)
    if re.fullmatch(r"[a-z]*[^aeiou]y", last):  # notify -> notifies, notified, notifying
        last_rx = f"{re.escape(last[:-1])}(?:y|ies|ied|ying)"
    elif last.endswith("e"):
        last_rx = f"{re.escape(last[:-1])}(?:e|es|ed|ing)"
    elif re.fullmatch(r"[a-z]+", last):
        last_rx = f"{stem}(?:s|es|ed|ing)?"
    else:  # abbreviations, hyphenated words, digits: match as written
        last_rx = stem
    return r"\s+".join([*(re.escape(w) for w in head), last_rx])


@dataclass(frozen=True)
class Concept:
    """One idea and the words that express it.

    ``pattern`` is for the rare concept a word list cannot express, such as "an email that is
    sent" (as opposed to an email address used as a login).
    """

    name: str
    terms: tuple[str, ...] = ()
    pattern: str | None = None
    _regex: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        alternatives = [_inflected(t) for t in sorted(self.terms, key=len, reverse=True)]
        if self.pattern:
            alternatives.append(f"(?:{self.pattern})")
        if not alternatives:
            raise ValueError(f"concept {self.name!r} needs terms or a pattern")
        regex = re.compile(r"(?<![\w-])(?:" + "|".join(alternatives) + r")(?![\w-])", re.I)
        object.__setattr__(self, "_regex", regex)

    def found_in(self, text: str) -> bool:
        return self._regex.search(text) is not None

    def matches(self, text: str) -> list[str]:
        """The distinct matched words, lower-cased, in order of appearance."""
        seen: dict[str, None] = {}
        for match in self._regex.finditer(text):
            seen.setdefault(" ".join(match.group(0).lower().split()), None)
        return list(seen)


# ------------------------------------------------------------------ shared vocabulary
# Statement shape
NEGATIVE_OUTCOME = Concept(
    "negative_outcome",
    terms=(
        "error", "invalid", "incorrect", "wrong", "fail", "failure", "reject", "denied", "deny",
        "block", "locked out", "must not", "should not", "shall not", "cannot", "can't",
        "not allowed", "not be allowed", "unable", "expired",
    ),
)  # fmt: skip
REQUIRED_INPUT = Concept("required_input", terms=("required", "mandatory"))
STATED_NUMERIC_LIMIT = Concept(
    "stated_numeric_limit",
    pattern=(
        r"(?:at least|at most|minimum(?: of)?|maximum(?: of)?|min|max|up to|no more than|"
        r"no fewer than|fewer than|less than|more than|between|exceed(?:s|ing)?|"
        r"limit(?:ed)? to|within)\s+\d+"
    ),
)
USER_INPUT = Concept(
    "user_input",
    terms=("enter", "input", "field", "form", "fill in", "password", "email address", "username"),
)

# Features with domain rules
OTP = Concept(
    "otp",
    terms=("otp", "one-time password", "one-time passcode", "one-time code", "verification code"),
)
MOBILE_NUMBER = Concept(
    "mobile_number", terms=("mobile number", "phone number", "mobile no", "cell number")
)
AUTHENTICATION = Concept(
    "authentication",
    terms=("log in", "login", "logs in", "sign in", "sign-in", "signs in", "authenticate"),
)
CART = Concept("cart", terms=("cart", "basket", "shopping bag"))
COUPON = Concept(
    "coupon", terms=("coupon", "discount code", "promo code", "promotion code", "voucher")
)
PAYMENT = Concept(
    "payment",
    terms=("payment", "pay", "paid", "card payment", "credit card", "debit card", "billing"),
)
EMAIL_SENT = Concept(
    "email_sent",
    pattern=(
        r"\b(?:send|sends|sent|receives?|received|deliver\w*|emailed)\b[^.\n]*\be-?mails?"
        r"|\be-?mail (?:notifications?|confirmations?|verification|links?|messages?)"
        r"|\b(?:confirmation|verification|welcome|reset) e-?mails?"
    ),
)
NOTIFICATION = Concept("notification", terms=("notification", "push notification", "notify"))
FILE_TRANSFER = Concept("file_transfer", terms=("upload", "download", "attachment", "file"))
DELETION = Concept("deletion", terms=("delete", "remove", "purge", "erase"))
PERSONAL_DATA = Concept(
    "personal_data",
    terms=("personal data", "personal details", "address", "date of birth", "profile", "pii"),
)
CONCURRENCY = Concept(
    "concurrency", terms=("concurrent", "simultaneous", "at the same time", "in parallel")
)
THIRD_PARTY = Concept("third_party", terms=("third-party", "external service", "integration"))

# Wording that cannot be verified as written (quality-attribute wording is in quality.py)
UNSPECIFIED_QUANTITY = Concept(
    "unspecified_quantity",
    terms=("large", "small", "many", "few", "several", "some", "various", "multiple"),
)
OPEN_ENDED = Concept(
    "open_ended",
    terms=("tbd", "tbc", "etc", "and/or", "as needed", "if possible", "where possible"),
)
QUALITY_JUDGEMENT = Concept(
    "quality_judgement",
    terms=(
        "appropriate", "appropriately", "adequate", "adequately", "reasonable", "robust",
        "flexible", "seamless", "seamlessly", "good", "better", "best", "optimal", "properly",
        "correctly", "normally", "usually", "typically",
    ),
)  # fmt: skip
