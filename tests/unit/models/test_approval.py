from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from autonomous_qa_agent.models import (
    ActionRisk,
    ApprovalDecision,
    ApprovalItem,
    ApprovalKind,
    ApprovalRequest,
)

ITEM = ApprovalItem(
    ref="delete", scenario_id="SC-2", summary="Delete task", risk=ActionRisk.DESTRUCTIVE
)


@pytest.fixture
def request_factory(t0: datetime, run_id: UUID) -> Any:
    def make(**overrides: Any) -> ApprovalRequest:
        data: dict[str, Any] = {
            "id": "AR-1",
            "run_id": run_id,
            "kind": ApprovalKind.PLAN,
            "items": (ITEM,),
            "created_at": t0,
            "expires_at": t0 + timedelta(hours=1),
        }
        return ApprovalRequest(**(data | overrides))

    return make


def test_request_expiry(request_factory: Any, t0: datetime) -> None:
    req: ApprovalRequest = request_factory()
    assert not req.is_expired(t0 + timedelta(minutes=59))
    assert req.is_expired(t0 + timedelta(hours=1))


def test_request_expiry_requires_aware_now(request_factory: Any, t0: datetime) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        request_factory().is_expired(t0.replace(tzinfo=None))


def test_request_validation(request_factory: Any, t0: datetime) -> None:
    with pytest.raises(ValidationError, match="after created_at"):
        request_factory(expires_at=t0)
    with pytest.raises(ValidationError):
        request_factory(items=())
    with pytest.raises(ValidationError, match="duplicate approval item refs"):
        request_factory(items=(ITEM, ITEM))


def test_rejection_requires_reason(t0: datetime) -> None:
    with pytest.raises(ValidationError, match="requires a reason"):
        ApprovalDecision(request_id="AR-1", approved=False, approver="qa-lead", decided_at=t0)
    decision = ApprovalDecision(
        request_id="AR-1",
        approved=False,
        approver="qa-lead",
        reason="Not on staging",
        decided_at=t0,
    )
    assert not decision.approved


def test_approval_without_reason_is_fine(t0: datetime) -> None:
    assert ApprovalDecision(request_id="AR-1", approved=True, approver="qa", decided_at=t0).approved
