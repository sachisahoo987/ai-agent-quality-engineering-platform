import pytest

from autonomous_qa_agent.agents.requirement_rules import analyse
from autonomous_qa_agent.agents.requirement_rules.statements import decompose, statements
from autonomous_qa_agent.models import Platform, Requirement


def requirement(description: str = "", criteria: tuple[str, ...] = ()) -> Requirement:
    return Requirement(
        id="REQ-1",
        title="t",
        platform=Platform.WEB,
        description=description,
        acceptance_criteria=criteria,
    )


@pytest.mark.parametrize(
    ("text", "clauses"),
    [
        (
            "A customer should be able to add products to the cart, apply a discount coupon "
            "and complete payment.",
            [
                "A customer should be able to add products to the cart.",
                "A customer should be able to apply a discount coupon.",
                "A customer should be able to complete payment.",
            ],
        ),
        (
            "Users can pay by card and receive a receipt",
            ["Users can pay by card", "Users can receive a receipt"],
        ),
        (
            "The admin must approve or reject the request!",
            ["The admin must approve the request!", "The admin must reject the request!"],
        ),
        (
            "Members can view, edit and delete their bookings.",
            [
                "Members can view their bookings.",
                "Members can edit their bookings.",
                "Members can delete their bookings.",
            ],
        ),
    ],
)
def test_compound_statements_split_into_one_clause_per_action(
    text: str, clauses: list[str]
) -> None:
    # Bare verbs share the last action's object ("approve or reject the request").
    assert decompose(text) == clauses


@pytest.mark.parametrize(
    "text",
    [
        "As a customer, I should log in using mobile number and OTP.",  # noun list
        "A user can sign in with a valid email and password",  # noun list
        "Search should be fast and user-friendly.",  # adjectives, not actions
        "A customer should be able to add products to the cart.",  # single action
        "Products and prices are shown on the page.",  # no modal verb
        "Users can add and remove",  # parts too short to be actions
    ],
)
def test_non_compound_statements_are_not_split(text: str) -> None:
    assert decompose(text) == [text]


def test_statements_prefer_acceptance_criteria() -> None:
    found = statements(requirement("The user can log in.", ("First", "Second", "first")))
    assert [(s.text, s.location) for s in found] == [
        ("First", "acceptance_criteria[0]"),
        ("Second", "acceptance_criteria[1]"),
    ]


def test_description_statements_need_behaviour_and_lose_list_markers() -> None:
    found = statements(
        requirement("Background info.\n- The task is shown in the list.\n1. Users can save.")
    )
    assert [s.text for s in found] == ["The task is shown in the list.", "Users can save."]
    assert {s.location for s in found} == {"description"}


def test_condition_ids_are_stable_when_statements_are_added() -> None:
    compound = "Users can add items to the cart and remove items from the cart."
    before = analyse(requirement(compound))
    after = analyse(requirement(f"{compound} Users can save the cart."))

    assert [c.id for c in before.conditions] == ["C-1.1", "C-1.2"]
    assert [c.id for c in after.conditions] == ["C-1.1", "C-1.2", "C-2"]
    assert [c.text for c in after.conditions[:2]] == [c.text for c in before.conditions]
