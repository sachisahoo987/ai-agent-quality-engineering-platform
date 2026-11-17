from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import Priority, TestScenario

Factory = Callable[..., Any]


def test_valid_scenario(make_scenario: Factory) -> None:
    scenario: TestScenario = make_scenario()
    assert scenario.priority is Priority.MEDIUM
    assert scenario.traces_to == ("C-1",)


@pytest.mark.parametrize("field", ["steps", "expected_results", "traces_to"])
def test_scenario_requires_non_empty_collections(make_scenario: Factory, field: str) -> None:
    with pytest.raises(ValidationError):
        make_scenario(**{field: ()})


def test_scenario_rejects_blank_steps(make_scenario: Factory) -> None:
    with pytest.raises(ValidationError):
        make_scenario(steps=("Open page", "   "))


def test_scenario_rejects_duplicate_traces(make_scenario: Factory) -> None:
    with pytest.raises(ValidationError, match="duplicate condition ids"):
        make_scenario(traces_to=("C-1", "C-1"))


def test_scenario_json_round_trip(make_scenario: Factory) -> None:
    scenario = make_scenario(tags=("smoke",))
    assert TestScenario.model_validate_json(scenario.model_dump_json()) == scenario
