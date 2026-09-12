"""Implementation of B01: Security context, capability leases, and durable execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .contracts import sha256_digest


class CancellationState(str, Enum):
    ACTIVE = "ACTIVE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class VerifiedSecurityContext:
    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str
    execution_epoch: int = 1
    fencing_generation: int = 1
    authority_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.project_id or not self.actor_id or not self.run_id:
            raise ValueError("SECURITY_CONTEXT_MISSING_REQUIRED_IDENTIFIERS")
        if self.execution_epoch < 1 or self.fencing_generation < 1:
            raise ValueError("INVALID_EPOCH_OR_FENCING_GENERATION")

    def bump_generation(self) -> VerifiedSecurityContext:
        return VerifiedSecurityContext(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            actor_id=self.actor_id,
            run_id=self.run_id,
            execution_epoch=self.execution_epoch,
            fencing_generation=self.fencing_generation + 1,
            authority_revision=self.authority_revision,
        )


@dataclass(frozen=True)
class CapabilityLease:
    lease_id: str
    tenant_id: str
    permissions: frozenset[str]
    ceiling: frozenset[str]
    expires_at: int
    revoked: bool = False

    def is_valid(self, now: int, required_permission: str) -> bool:
        if self.revoked:
            return False
        if now >= self.expires_at:
            return False
        if required_permission not in self.permissions:
            return False
        if required_permission not in self.ceiling:
            return False
        return True


@dataclass
class DurableExecutionSession:
    """Manages epoch fencing, idempotency keys, and cancellation lifecycle."""
    tenant_id: str
    run_id: str
    context: VerifiedSecurityContext
    cancellation_state: CancellationState = CancellationState.ACTIVE
    committed_idempotency_keys: dict[str, dict[str, Any]] = field(default_factory=dict)

    def request_cancellation(self) -> None:
        self.cancellation_state = CancellationState.CANCEL_REQUESTED
        self.context = self.context.bump_generation()

    def confirm_cancellation(self) -> None:
        self.cancellation_state = CancellationState.CANCELLED

    def commit_idempotent_step(
        self,
        step_id: str,
        idempotency_key: str,
        fencing_generation: int,
        result_payload: Any,
    ) -> dict[str, Any]:
        if self.cancellation_state in (CancellationState.CANCEL_REQUESTED, CancellationState.CANCELLED):
            raise ValueError("EXECUTION_CANCELLED_OR_REQUESTED")

        if fencing_generation < self.context.fencing_generation:
            raise ValueError(
                f"FENCING_GENERATION_REJECTED: received {fencing_generation}, active {self.context.fencing_generation}"
            )

        composite_key = f"{self.tenant_id}:{self.run_id}:{step_id}:{idempotency_key}"
        if composite_key in self.committed_idempotency_keys:
            # Idempotent replay: return cached result
            return self.committed_idempotency_keys[composite_key]

        record = {
            "step_id": step_id,
            "idempotency_key": idempotency_key,
            "fencing_generation": fencing_generation,
            "payload": result_payload,
            "digest": sha256_digest(result_payload),
        }
        self.committed_idempotency_keys[composite_key] = record
        return record
