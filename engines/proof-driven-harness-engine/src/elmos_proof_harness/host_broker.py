"""Host Broker, Capability Lease Verification, and Two-Phase External Effect Settlement.

Provides a trusted execution boundary for external providers, capability lease fencing,
and transactional 2PC escrow settlement (PREPARE, COMMIT, ROLLBACK).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


class SettlementStatus(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class CapabilityLease:
    lease_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    purpose: str
    permissions: tuple[str, ...]
    generation_fence: int
    issued_at: str
    expires_at: str

    def is_expired(self, current_time: datetime | None = None) -> bool:
        now = current_time or datetime.now(UTC)
        exp = datetime.fromisoformat(self.expires_at)
        return now > exp

    @property
    def digest(self) -> str:
        payload = {
            "lease_id": self.lease_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "purpose": self.purpose,
            "permissions": list(sorted(self.permissions)),
            "generation_fence": self.generation_fence,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class CapabilityLeaseVerifier:
    """Enforces fail-closed validation of capability leases before external dispatch."""

    def __init__(self, allowed_tenants: Sequence[str] | None = None) -> None:
        self.allowed_tenants = set(allowed_tenants) if allowed_tenants else None

    def verify(
        self,
        lease: CapabilityLease,
        required_permission: str,
        current_generation: int,
        current_time: datetime | None = None,
    ) -> None:
        now = current_time or datetime.now(UTC)
        if lease.is_expired(now):
            raise PermissionError(f"capability lease {lease.lease_id} has expired at {lease.expires_at}")

        if self.allowed_tenants is not None and lease.tenant_id not in self.allowed_tenants:
            raise PermissionError(f"tenant {lease.tenant_id} is not allowlisted for external capability")

        if lease.generation_fence < current_generation:
            raise PermissionError(
                f"stale generation fence: lease {lease.generation_fence} < current {current_generation}"
            )

        if required_permission not in lease.permissions:
            raise PermissionError(
                f"lease {lease.lease_id} lacks required permission: '{required_permission}'"
            )


@dataclass(frozen=True)
class EffectSettlementReceipt:
    escrow_id: str
    lease_id: str
    tenant_id: str
    operation: str
    cost_tokens: int
    cost_cents: int
    status: SettlementStatus
    prepared_at: str
    settled_at: str
    execution_receipt_digest: str | None
    refund_reason: str | None = None

    @property
    def digest(self) -> str:
        payload = {
            "escrow_id": self.escrow_id,
            "lease_id": self.lease_id,
            "tenant_id": self.tenant_id,
            "operation": self.operation,
            "cost_tokens": self.cost_tokens,
            "cost_cents": self.cost_cents,
            "status": self.status.value,
            "prepared_at": self.prepared_at,
            "settled_at": self.settled_at,
            "execution_receipt_digest": self.execution_receipt_digest,
            "refund_reason": self.refund_reason,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class SettlementLedger:
    """Two-Phase (2PC) atomic escrow ledger for external tool / LLM side effects."""

    def __init__(self) -> None:
        self._escrows: dict[str, dict[str, Any]] = {}
        self._settled: dict[str, EffectSettlementReceipt] = {}

    def prepare(
        self,
        escrow_id: str,
        lease: CapabilityLease,
        operation: str,
        cost_tokens: int,
        cost_cents: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if escrow_id in self._escrows or escrow_id in self._settled:
            raise ValueError(f"escrow {escrow_id} already exists")

        now = datetime.now(UTC).isoformat()
        self._escrows[escrow_id] = {
            "lease": lease,
            "operation": operation,
            "cost_tokens": cost_tokens,
            "cost_cents": cost_cents,
            "status": SettlementStatus.RESERVED,
            "prepared_at": now,
            "metadata": dict(metadata or {}),
        }
        return escrow_id

    def commit(
        self,
        escrow_id: str,
        execution_receipt_digest: str,
    ) -> EffectSettlementReceipt:
        if escrow_id not in self._escrows:
            raise KeyError(f"escrow {escrow_id} not found in prepare phase")

        rec = self._escrows.pop(escrow_id)
        lease: CapabilityLease = rec["lease"]
        now = datetime.now(UTC).isoformat()
        receipt = EffectSettlementReceipt(
            escrow_id=escrow_id,
            lease_id=lease.lease_id,
            tenant_id=lease.tenant_id,
            operation=rec["operation"],
            cost_tokens=rec["cost_tokens"],
            cost_cents=rec["cost_cents"],
            status=SettlementStatus.COMMITTED,
            prepared_at=rec["prepared_at"],
            settled_at=now,
            execution_receipt_digest=execution_receipt_digest,
        )
        self._settled[escrow_id] = receipt
        return receipt

    def rollback(
        self,
        escrow_id: str,
        reason: str,
    ) -> EffectSettlementReceipt:
        if escrow_id not in self._escrows:
            raise KeyError(f"escrow {escrow_id} not found in prepare phase")

        rec = self._escrows.pop(escrow_id)
        lease: CapabilityLease = rec["lease"]
        now = datetime.now(UTC).isoformat()
        receipt = EffectSettlementReceipt(
            escrow_id=escrow_id,
            lease_id=lease.lease_id,
            tenant_id=lease.tenant_id,
            operation=rec["operation"],
            cost_tokens=0,
            cost_cents=0,
            status=SettlementStatus.ROLLED_BACK,
            prepared_at=rec["prepared_at"],
            settled_at=now,
            execution_receipt_digest=None,
            refund_reason=reason,
        )
        self._settled[escrow_id] = receipt
        return receipt

    def get_receipt(self, escrow_id: str) -> EffectSettlementReceipt | None:
        return self._settled.get(escrow_id)


class HostBrokerChannel:
    """Safe mediated broker for invoking external providers under strict lease and 2PC settlement."""

    def __init__(
        self,
        lease_verifier: CapabilityLeaseVerifier | None = None,
        settlement_ledger: SettlementLedger | None = None,
    ) -> None:
        self.verifier = lease_verifier or CapabilityLeaseVerifier()
        self.ledger = settlement_ledger or SettlementLedger()
        self._handlers: dict[str, Callable[[Mapping[str, Any]], Mapping[str, Any]]] = {}

    def register_provider(
        self,
        capability: str,
        handler: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    ) -> None:
        self._handlers[capability] = handler

    def execute_brokered(
        self,
        capability: str,
        payload: Mapping[str, Any],
        lease: CapabilityLease,
        current_generation: int,
        cost_tokens: int = 100,
        cost_cents: int = 1,
    ) -> tuple[Mapping[str, Any], EffectSettlementReceipt]:
        # 1. Verify capability lease
        self.verifier.verify(lease, required_permission=capability, current_generation=current_generation)

        if capability not in self._handlers:
            raise NotImplementedError(f"no host provider registered for brokered capability '{capability}'")

        escrow_id = f"escrow:{lease.tenant_id}:{hashlib.sha256(f'{lease.lease_id}:{time.time_ns()}'.encode()).hexdigest()[:16]}"
        self.ledger.prepare(
            escrow_id=escrow_id,
            lease=lease,
            operation=capability,
            cost_tokens=cost_tokens,
            cost_cents=cost_cents,
        )

        try:
            handler = self._handlers[capability]
            result = handler(payload)
            receipt_digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            receipt = self.ledger.commit(escrow_id, execution_receipt_digest=receipt_digest)
            return result, receipt
        except Exception as exc:
            receipt = self.ledger.rollback(escrow_id, reason=str(exc))
            raise RuntimeError(f"brokered execution failed, escrow rolled back: {exc}") from exc
