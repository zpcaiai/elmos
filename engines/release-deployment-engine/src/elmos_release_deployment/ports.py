"""Host-owned authorities. Application/client JSON never supplies implementations."""
from __future__ import annotations
from typing import Protocol
from .contracts import CapabilityLease, Principal, Scope


class TrustVerifier(Protocol):
    def verify(self, purpose: str, body: dict, signature: str) -> bool:
        """Verify exact canonical bytes with pinned, non-revoked authority keys."""
        ...


class AuthorizationHost(Protocol):
    def authorize(self, principal: Principal, action: str, body: dict) -> dict:
        """Return signed ticket/approval after canonical host policy and RBAC checks."""
        ...

    def lease(self, principal: Principal, deployment_id: str, plan_digest: str,
              resources: tuple[str, ...], action: str, generation: int) -> CapabilityLease:
        ...


class ExecutionHost(Protocol):
    """Bridge to ProductionToolCallPort + credential/runner adapters.

    submit must atomically claim the host tool-call dispatch before sending.
    recover must reconcile the same exact request/operation key; never blindly
    resubmit. UNKNOWN (including not-found that cannot prove non-dispatch) is
    pending. Provider receipts are independently byte-bound by TrustVerifier.
    """
    def submit(self, request: dict, lease: CapabilityLease) -> str: ...
    def recover(self, request: dict, lease: CapabilityLease) -> str | None: ...
    def poll(self, invocation_id: str, request: dict, lease: CapabilityLease) -> dict | None: ...


class EvidenceHost(Protocol):
    def commit(self, scope: Scope, operation_key: str, bundle: dict) -> dict:
        """Idempotent immutable CAS + evidence fabric commit; return signed receipt."""
        ...
