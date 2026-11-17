from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    ActionRisk,
    ActionType,
    DeviceProfile,
    DriverKind,
    ExecutableStep,
    ExecutionPlan,
    Locator,
    LocatorStrategy,
    Platform,
    TargetEnvironment,
)

Factory = Callable[..., Any]


# ------------------------------------------------------------------ environment
def _device(platform: Platform = Platform.ANDROID) -> DeviceProfile:
    return DeviceProfile(platform=platform, device_name="Pixel 8", app_id="com.example.app")


def test_device_profile_requires_mobile_platform() -> None:
    with pytest.raises(ValidationError, match="mobile platform"):
        _device(Platform.WEB)


def test_web_environment_requires_base_url() -> None:
    with pytest.raises(ValidationError, match="base_url"):
        TargetEnvironment(name="web", platform=Platform.WEB)


def test_mobile_environment_requires_matching_device() -> None:
    TargetEnvironment(name="android", platform=Platform.ANDROID, device=_device())
    with pytest.raises(ValidationError, match="device profile"):
        TargetEnvironment(name="android", platform=Platform.ANDROID)
    with pytest.raises(ValidationError, match="does not match"):
        TargetEnvironment(name="ios", platform=Platform.IOS, device=_device(Platform.ANDROID))


def test_production_environment_cannot_be_disposable() -> None:
    with pytest.raises(ValidationError, match="cannot be disposable"):
        TargetEnvironment(
            name="prod",
            platform=Platform.WEB,
            base_url="https://example.com",
            is_production=True,
            disposable=True,
        )


def test_environment_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        TargetEnvironment(name="web", platform=Platform.WEB, base_url="not a url")


# ------------------------------------------------------------------ locator
def test_locator_with_distinct_fallbacks() -> None:
    loc = Locator(
        strategy=LocatorStrategy.ROLE,
        value="button[name=Save]",
        fallbacks=(Locator(strategy=LocatorStrategy.TEST_ID, value="save"),),
    )
    assert len(loc.fallbacks) == 1


def test_locator_rejects_fallback_equal_to_primary() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        Locator(
            strategy=LocatorStrategy.CSS,
            value="#save",
            fallbacks=(Locator(strategy=LocatorStrategy.CSS, value="#save"),),
        )


def test_locator_rejects_nested_fallbacks() -> None:
    nested = Locator(
        strategy=LocatorStrategy.CSS,
        value="#a",
        fallbacks=(Locator(strategy=LocatorStrategy.CSS, value="#b"),),
    )
    with pytest.raises(ValidationError, match="their own fallbacks"):
        Locator(strategy=LocatorStrategy.TEXT, value="Save", fallbacks=(nested,))


def test_locator_rejects_blank_value() -> None:
    with pytest.raises(ValidationError):
        Locator(strategy=LocatorStrategy.CSS, value="  ")


# ------------------------------------------------------------------ executable step
def test_step_risk_is_mandatory(locator: Locator) -> None:
    with pytest.raises(ValidationError, match="risk"):
        ExecutableStep(id="s", action=ActionType.CLICK, locator=locator)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"action": ActionType.CLICK, "locator": None}, "requires a locator"),
        ({"action": ActionType.ASSERT_TEXT}, "requires an expected value"),
        ({"action": ActionType.FILL}, "requires a value"),
        ({"action": ActionType.NAVIGATE, "locator": None}, "requires a value"),
        ({"action": ActionType.ASSERT_URL, "locator": None}, "requires an expected value"),
        (
            {"action": ActionType.FILL, "value": "x", "secret_ref": "APP_PASSWORD"},
            "mutually exclusive",
        ),
        ({"action": ActionType.CLICK, "secret_ref": "APP_PASSWORD"}, "does not accept"),
    ],
)
def test_step_action_requirements(
    make_step: Factory, overrides: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_step(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": ActionType.NAVIGATE, "locator": None, "value": "/tasks"},
        {"action": ActionType.FILL, "value": ""},  # clearing a field is legitimate
        {"action": ActionType.FILL, "secret_ref": "APP_PASSWORD"},
        {"action": ActionType.ASSERT_TEXT, "expected": "Saved"},
        {"action": ActionType.ASSERT_URL, "locator": None, "expected": "/tasks/1"},
        {"action": ActionType.SCREENSHOT, "locator": None},
        {"action": ActionType.SWIPE, "locator": None, "value": "up"},
    ],
)
def test_step_valid_combinations(make_step: Factory, overrides: dict[str, Any]) -> None:
    make_step(**overrides)


@pytest.mark.parametrize("ref", ["app_password", "1PASSWORD", "HAS-DASH", ""])
def test_step_secret_ref_must_be_env_style(make_step: Factory, ref: str) -> None:
    with pytest.raises(ValidationError):
        make_step(action=ActionType.FILL, secret_ref=ref)


@pytest.mark.parametrize("timeout", [0, -1, 300_001])
def test_step_timeout_bounds(make_step: Factory, timeout: int) -> None:
    with pytest.raises(ValidationError):
        make_step(timeout_ms=timeout)


def test_secret_value_never_appears_in_serialised_step(make_step: Factory) -> None:
    step = make_step(action=ActionType.FILL, secret_ref="APP_PASSWORD")
    assert step.value is None
    assert "APP_PASSWORD" in step.model_dump_json()  # only the reference is stored


# ------------------------------------------------------------------ planned test
def test_planned_test_rejects_duplicate_step_ids(
    make_planned_test: Factory, make_step: Factory
) -> None:
    with pytest.raises(ValidationError, match="duplicate step ids"):
        make_planned_test(steps=(make_step(), make_step()))


def test_playwright_cannot_tap(make_planned_test: Factory, make_step: Factory) -> None:
    with pytest.raises(ValidationError, match="mobile-only"):
        make_planned_test(steps=(make_step(action=ActionType.TAP),))


def test_appium_can_tap(make_planned_test: Factory, make_step: Factory) -> None:
    test = make_planned_test(driver=DriverKind.APPIUM, steps=(make_step(action=ActionType.TAP),))
    assert test.steps[0].action is ActionType.TAP


def test_planned_test_requires_steps_and_bounded_retries(make_planned_test: Factory) -> None:
    with pytest.raises(ValidationError):
        make_planned_test(steps=())
    with pytest.raises(ValidationError):
        make_planned_test(max_retries=4)


# ------------------------------------------------------------------ plan
def test_plan_risk_summary(
    make_plan: Factory, make_planned_test: Factory, make_step: Factory
) -> None:
    risky = make_step(id="delete", risk=ActionRisk.DESTRUCTIVE)
    plan: ExecutionPlan = make_plan(
        tests=(
            make_planned_test(scenario_id="SC-1"),
            make_planned_test(
                scenario_id="SC-2",
                steps=(make_step(), make_step(id="save", risk=ActionRisk.STATE_CHANGING), risky),
            ),
        )
    )
    assert plan.highest_risk is ActionRisk.DESTRUCTIVE
    assert [(sid, s.id) for sid, s in plan.risky_steps] == [("SC-2", "save"), ("SC-2", "delete")]


def test_read_only_plan_has_no_risky_steps(make_plan: Factory) -> None:
    plan: ExecutionPlan = make_plan()
    assert plan.highest_risk is ActionRisk.READ_ONLY
    assert plan.risky_steps == ()


def test_plan_rejects_duplicate_scenarios(make_plan: Factory, make_planned_test: Factory) -> None:
    with pytest.raises(ValidationError, match="duplicate scenario ids"):
        make_plan(tests=(make_planned_test(), make_planned_test()))


def test_plan_driver_must_match_platform(make_plan: Factory, make_planned_test: Factory) -> None:
    with pytest.raises(ValidationError, match="appium"):
        make_plan(
            environment=TargetEnvironment(name="a", platform=Platform.ANDROID, device=_device()),
            tests=(make_planned_test(),),
        )


def test_plan_json_round_trip(make_plan: Factory) -> None:
    plan: ExecutionPlan = make_plan()
    assert ExecutionPlan.model_validate_json(plan.model_dump_json()) == plan
