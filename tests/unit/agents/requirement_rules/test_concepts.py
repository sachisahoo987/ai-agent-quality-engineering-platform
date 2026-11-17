import pytest

from autonomous_qa_agent.agents.requirement_rules.concepts import EMAIL_SENT, Concept


@pytest.mark.parametrize(
    ("term", "text"),
    [
        ("delete", "Deleting a task"),
        ("delete", "the task is deleted"),
        ("coupon", "two coupons"),
        ("notify", "users are notified"),
        ("notify", "the app notifies users"),
        ("log in", "users can log  in"),
        ("otp", "Enter the OTP"),
        ("and/or", "email and/or phone"),
    ],
)
def test_terms_match_inflections_and_case(term: str, text: str) -> None:
    assert Concept("c", terms=(term,)).found_in(text)


@pytest.mark.parametrize(
    ("term", "text"),
    [("load", "upload a file"), ("pay", "payroll report"), ("cart", "carton"), ("e", "e-mail")],
)
def test_terms_match_whole_words_only(term: str, text: str) -> None:
    assert not Concept("c", terms=(term,)).found_in(text)


def test_matches_returns_distinct_normalised_words() -> None:
    concept = Concept("c", terms=("fast", "quick"))
    assert concept.matches("Fast, FAST and quick") == ["fast", "quick"]


def test_pattern_concept_distinguishes_sent_email_from_an_address() -> None:
    assert EMAIL_SENT.found_in("A confirmation email is sent")
    assert EMAIL_SENT.found_in("Users receive a welcome email")
    assert not EMAIL_SENT.found_in("Users sign in with their email and password")


def test_concept_needs_terms_or_a_pattern() -> None:
    with pytest.raises(ValueError, match="needs terms or a pattern"):
        Concept("empty")
