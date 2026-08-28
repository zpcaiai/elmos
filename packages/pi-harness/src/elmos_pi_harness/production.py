"""Shared fail-closed contracts for production-facing PI Harness adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .canonical import digest, require_nonempty, require_uuid, utc_now
from .models import ConflictError, PolicyDeniedError


class OperationState(str, Enum):
    PREPARED = "PREPARED"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    ROLLED_BACK = "ROLLED_BACK"
    DESTROYED = "DESTROYED"


class ExternalEvidenceState(str, Enum):
    NOT_RUN = "NOT_RUN"
    EXECUTED = "EXECUTED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ExactTarget:
    provider: str
    service: str
    version: str
    region: str
    account_id: str
    environment: str

    def __post_init__(self) -> None:
        for field_name in (
            "provider",
            "service",
            "version",
            "region",
            "account_id",
            "environment",
        ):
            require_nonempty(getattr(self, field_name), field_name, 256)

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "service": self.service,
            "version": self.version,
            "region": self.region,
            "account_id": self.account_id,
            "environment": self.environment,
        }


@dataclass(frozen=True)
class ApprovalGrant:
    approval_id: str
    operation_id: str
    request_digest: str
    target_digest: str
    approved_by: str
    expires_at: str
    allowed_action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_uuid(self.approval_id, "approval_id")
        require_uuid(self.operation_id, "operation_id")
        require_nonempty(self.request_digest, "request_digest", 128)
        require_nonempty(self.target_digest, "target_digest", 128)
        require_nonempty(self.approved_by, "approved_by", 256)
        require_nonempty(self.allowed_action, "allowed_action", 128)
        _parse_time(self.expires_at, "expires_at")

    def assert_valid(
        self,
        *,
        operation_id: str,
        request_digest: str,
        target: ExactTarget,
        action: str,
        actor_id: str,
    ) -> None:
        if self.operation_id != operation_id or self.request_digest != request_digest:
            raise PolicyDeniedError("approval does not bind the requested operation")
        if (
            self.target_digest != digest(target.to_dict())
            or self.allowed_action != action
        ):
            raise PolicyDeniedError(
                "approval does not bind the exact target and action"
            )
        if self.approved_by == actor_id:
            raise PolicyDeniedError(
                "request actor cannot self-approve an external effect"
            )
        if _parse_time(self.expires_at, "expires_at") <= datetime.now(timezone.utc):
            raise PolicyDeniedError("approval has expired")


@dataclass(frozen=True)
class OperationReceipt:
    operation_id: str
    target: ExactTarget
    action: str
    request_digest: str
    state: OperationState
    provider_native_id: str | None = None
    native_evidence_digest: str | None = None
    normalized_evidence_digest: str | None = None
    reconciliation_required: bool = False
    observed_at: str = field(default_factory=utc_now)
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_uuid(self.operation_id, "operation_id")
        require_nonempty(self.action, "action", 128)
        require_nonempty(self.request_digest, "request_digest", 128)
        if (
            self.state
            in {OperationState.UNKNOWN, OperationState.RECONCILIATION_REQUIRED}
            and not self.reconciliation_required
        ):
            raise ValueError("unknown provider outcomes must require reconciliation")
        if self.state == OperationState.SUCCEEDED and not self.provider_native_id:
            raise ValueError(
                "successful provider effects require a native operation id"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "target": self.target.to_dict(),
            "action": self.action,
            "request_digest": self.request_digest,
            "state": self.state.value,
            "provider_native_id": self.provider_native_id,
            "native_evidence_digest": self.native_evidence_digest,
            "normalized_evidence_digest": self.normalized_evidence_digest,
            "reconciliation_required": self.reconciliation_required,
            "observed_at": self.observed_at,
            "limitations": list(self.limitations),
        }


def assert_monotonic_state(current: OperationState, target: OperationState) -> None:
    allowed = {
        OperationState.PREPARED: {OperationState.APPROVED, OperationState.FAILED},
        OperationState.APPROVED: {OperationState.SUBMITTED, OperationState.FAILED},
        OperationState.SUBMITTED: {
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.UNKNOWN,
        },
        OperationState.UNKNOWN: {OperationState.RECONCILIATION_REQUIRED},
        OperationState.RECONCILIATION_REQUIRED: {
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.UNKNOWN,
            OperationState.ROLLED_BACK,
            OperationState.DESTROYED,
        },
        OperationState.SUCCEEDED: {
            OperationState.ROLLED_BACK,
            OperationState.DESTROYED,
            OperationState.RECONCILIATION_REQUIRED,
        },
        OperationState.FAILED: set(),
        OperationState.ROLLED_BACK: {
            OperationState.DESTROYED,
            OperationState.RECONCILIATION_REQUIRED,
        },
        OperationState.DESTROYED: set(),
    }
    if target not in allowed[current]:
        raise ConflictError(
            f"invalid production operation transition {current.value}->{target.value}"
        )


def _parse_time(value: str, field_name: str) -> datetime:
    require_nonempty(value, field_name, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)
