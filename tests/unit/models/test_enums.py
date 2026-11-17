import pytest

from autonomous_qa_agent.models import (
    ActionRisk,
    DriverKind,
    Platform,
    RunStatus,
    TestStatus,
    highest_risk,
)
from autonomous_qa_agent.models.enums import (
    EXPECTED_REQUIRED_ACTIONS,
    LOCATOR_REQUIRED_ACTIONS,
    MOBILE_ONLY_ACTIONS,
    SECRET_CAPABLE_ACTIONS,
    VALUE_REQUIRED_ACTIONS,
    ActionType,
)


@pytest.mark.parametrize(
    ("platform", "mobile", "driver"),
    [
        (Platform.WEB, False, DriverKind.PLAYWRIGHT),
        (Platform.ANDROID, True, DriverKind.APPIUM),
        (Platform.IOS, True, DriverKind.APPIUM),
    ],
)
def test_platform_maps_to_driver(platform: Platform, mobile: bool, driver: DriverKind) -> None:
    assert platform.is_mobile is mobile
    assert platform.driver is driver


def test_risk_rank_orders_by_severity_not_by_string() -> None:
    assert ActionRisk.READ_ONLY.rank < ActionRisk.STATE_CHANGING.rank < ActionRisk.DESTRUCTIVE.rank


@pytest.mark.parametrize(
    ("risks", "expected"),
    [
        ([], ActionRisk.READ_ONLY),
        ([ActionRisk.READ_ONLY], ActionRisk.READ_ONLY),
        ([ActionRisk.DESTRUCTIVE, ActionRisk.READ_ONLY], ActionRisk.DESTRUCTIVE),
        ([ActionRisk.READ_ONLY, ActionRisk.STATE_CHANGING], ActionRisk.STATE_CHANGING),
    ],
)
def test_highest_risk(risks: list[ActionRisk], expected: ActionRisk) -> None:
    assert highest_risk(risks) is expected


def test_failure_statuses() -> None:
    assert {s for s in TestStatus if s.is_failure} == {TestStatus.FAILED, TestStatus.ERROR}


def test_terminal_run_statuses() -> None:
    assert {s for s in RunStatus if not s.is_terminal} == {
        RunStatus.PENDING,
        RunStatus.RUNNING,
        RunStatus.AWAITING_APPROVAL,
    }


def test_capability_tables_are_consistent() -> None:
    every_action = set(ActionType)
    for table in (
        LOCATOR_REQUIRED_ACTIONS,
        VALUE_REQUIRED_ACTIONS,
        EXPECTED_REQUIRED_ACTIONS,
        MOBILE_ONLY_ACTIONS,
        SECRET_CAPABLE_ACTIONS,
    ):
        assert table <= every_action
    assert SECRET_CAPABLE_ACTIONS <= VALUE_REQUIRED_ACTIONS
    assert ActionType.SCREENSHOT not in LOCATOR_REQUIRED_ACTIONS | VALUE_REQUIRED_ACTIONS
