"""Execution planning contracts: target environment, locators, executable steps, plans."""

from typing import Self
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from autonomous_qa_agent.models.common import (
    ContractModel,
    Identifier,
    NonEmptyStr,
    SecretRef,
    find_duplicates,
)
from autonomous_qa_agent.models.enums import (
    EXPECTED_REQUIRED_ACTIONS,
    LOCATOR_REQUIRED_ACTIONS,
    MOBILE_ONLY_ACTIONS,
    SECRET_CAPABLE_ACTIONS,
    VALUE_REQUIRED_ACTIONS,
    ActionRisk,
    ActionType,
    DriverKind,
    LocatorStrategy,
    Platform,
    highest_risk,
)


class DeviceProfile(ContractModel):
    """Mobile device or emulator to run Appium tests on."""

    platform: Platform
    device_name: NonEmptyStr
    platform_version: str | None = None
    app_id: NonEmptyStr  # Android package name or iOS bundle id

    @model_validator(mode="after")
    def _mobile_only(self) -> Self:
        if not self.platform.is_mobile:
            raise ValueError("a device profile requires a mobile platform")
        return self


class TargetEnvironment(ContractModel):
    """Where tests run. Production targets are representable so the guard can refuse them."""

    name: Identifier
    platform: Platform
    base_url: HttpUrl | None = None
    device: DeviceProfile | None = None
    is_production: bool = False
    disposable: bool = False  # data may be freely created and destroyed

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.platform is Platform.WEB and self.base_url is None:
            raise ValueError("a web environment requires base_url")
        if self.platform.is_mobile:
            if self.device is None:
                raise ValueError("a mobile environment requires a device profile")
            if self.device.platform is not self.platform:
                raise ValueError("device platform does not match environment platform")
        if self.is_production and self.disposable:
            raise ValueError("a production environment cannot be disposable")
        return self


class Locator(ContractModel):
    """How to find an element, with optional ordered fallbacks (one level deep)."""

    strategy: LocatorStrategy
    value: NonEmptyStr
    fallbacks: tuple["Locator", ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def _valid_fallbacks(self) -> Self:
        if any(f.fallbacks for f in self.fallbacks):
            raise ValueError("fallback locators cannot have their own fallbacks")
        keys = [(self.strategy, self.value), *((f.strategy, f.value) for f in self.fallbacks)]
        if len(set(keys)) != len(keys):
            raise ValueError("fallback locators must differ from the primary and each other")
        return self


class ExecutableStep(ContractModel):
    """One deterministic action the executor maps onto exactly one tool call.

    ``risk`` is mandatory: nothing is assumed safe by default.
    """

    id: Identifier
    action: ActionType
    risk: ActionRisk
    description: str = Field(default="", max_length=500)
    locator: Locator | None = None
    value: str | None = Field(default=None, max_length=10_000)
    secret_ref: SecretRef | None = None
    expected: str | None = Field(default=None, max_length=10_000)
    timeout_ms: int = Field(default=10_000, gt=0, le=300_000)

    @model_validator(mode="after")
    def _action_requirements(self) -> Self:
        problems: list[str] = []
        action = self.action
        if action in LOCATOR_REQUIRED_ACTIONS and self.locator is None:
            problems.append(f"{action} requires a locator")
        if self.value is not None and self.secret_ref is not None:
            problems.append("value and secret_ref are mutually exclusive")
        if self.secret_ref is not None and action not in SECRET_CAPABLE_ACTIONS:
            problems.append(f"{action} does not accept a secret_ref")
        if action in VALUE_REQUIRED_ACTIONS and self.value is None and self.secret_ref is None:
            problems.append(f"{action} requires a value")
        if action in EXPECTED_REQUIRED_ACTIONS and self.expected is None:
            problems.append(f"{action} requires an expected value")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class PlannedTest(ContractModel):
    """A scenario compiled into executable steps for one driver."""

    __test__ = False

    scenario_id: Identifier
    driver: DriverKind
    steps: tuple[ExecutableStep, ...] = Field(min_length=1, max_length=200)
    max_retries: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if duplicated := find_duplicates(s.id for s in self.steps):
            raise ValueError(f"duplicate step ids: {duplicated}")
        if self.driver is DriverKind.PLAYWRIGHT and (
            unsupported := sorted({s.action for s in self.steps} & MOBILE_ONLY_ACTIONS)
        ):
            raise ValueError(f"playwright cannot perform mobile-only actions: {unsupported}")
        return self

    @property
    def highest_risk(self) -> ActionRisk:
        return highest_risk(s.risk for s in self.steps)


class ExecutionPlan(ContractModel):
    """Everything the executor will do in a run. Approvals are granted against this plan."""

    run_id: UUID
    environment: TargetEnvironment
    tests: tuple[PlannedTest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if duplicated := find_duplicates(t.scenario_id for t in self.tests):
            raise ValueError(f"duplicate scenario ids in plan: {duplicated}")
        expected_driver = self.environment.platform.driver
        if mismatched := [t.scenario_id for t in self.tests if t.driver is not expected_driver]:
            raise ValueError(
                f"tests {mismatched} do not use the {expected_driver} driver required by "
                f"the {self.environment.platform} environment"
            )
        return self

    @property
    def highest_risk(self) -> ActionRisk:
        return highest_risk(t.highest_risk for t in self.tests)

    @property
    def risky_steps(self) -> tuple[tuple[str, ExecutableStep], ...]:
        """(scenario_id, step) for every step that is not read-only, in plan order."""
        return tuple(
            (test.scenario_id, step)
            for test in self.tests
            for step in test.steps
            if step.risk is not ActionRisk.READ_ONLY
        )
