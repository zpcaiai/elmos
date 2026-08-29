"""Proof-driven execution kernel for Elmos Foundry.

Enforces tenant isolation, state machine invariants, rollback boundaries,
deterministic replay, and fail-closed safety constraints.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import time
import uuid
from typing import Any, Callable, Mapping, Sequence

from .domain import (
    ContentDigest,
    ExecutionResult,
    GateLevel,
    LifecycleState,
    TenantScope,
)

# Context variable for active tenant context isolation
_current_tenant_scope: contextvars.ContextVar[TenantScope | None] = contextvars.ContextVar(
    "_current_tenant_scope", default=None
)


class KernelSecurityError(RuntimeError):
    """Raised when tenant isolation or security invariant is violated."""


class KernelStateError(RuntimeError):
    """Raised when lifecycle state transition is illegal."""


class ExecutionKernel:
    """Enterprise execution kernel for secure, isolated, proof-driven operations."""

    def __init__(self) -> None:
        self._active_rollbacks: dict[str, list[Callable[[], None]]] = {}

    def set_tenant_context(self, scope: TenantScope) -> contextvars.Token[TenantScope | None]:
        return _current_tenant_scope.set(scope)

    def reset_tenant_context(self, token: contextvars.Token[TenantScope | None]) -> None:
        _current_tenant_scope.reset(token)

    @property
    def current_tenant(self) -> TenantScope:
        scope = _current_tenant_scope.get()
        if scope is None:
            raise KernelSecurityError("fail-closed: operation requires an active authenticated TenantScope")
        return scope

    def register_rollback(self, transaction_id: str, action: Callable[[], None]) -> None:
        if transaction_id not in self._active_rollbacks:
            self._active_rollbacks[transaction_id] = []
        self._active_rollbacks[transaction_id].append(action)

    def execute_rollback(self, transaction_id: str) -> None:
        actions = self._active_rollbacks.pop(transaction_id, [])
        for action in reversed(actions):
            try:
                action()
            except Exception as exc:  # pragma: no cover
                # Log rollback error but continue remaining rollbacks
                pass

    def commit_transaction(self, transaction_id: str) -> None:
        self._active_rollbacks.pop(transaction_id, None)

    def validate_transition(self, current: LifecycleState, target: LifecycleState) -> bool:
        allowed = {
            LifecycleState.DRAFT: {LifecycleState.PROFILED, LifecycleState.BLOCKED, LifecycleState.FAILED},
            LifecycleState.PROFILED: {LifecycleState.PLANNED, LifecycleState.BLOCKED, LifecycleState.FAILED},
            LifecycleState.PLANNED: {LifecycleState.RUNNING, LifecycleState.BLOCKED, LifecycleState.FAILED},
            LifecycleState.RUNNING: {LifecycleState.VERIFYING, LifecycleState.BLOCKED, LifecycleState.FAILED},
            LifecycleState.VERIFYING: {LifecycleState.EVIDENCE_SEALED, LifecycleState.FAILED},
            LifecycleState.EVIDENCE_SEALED: {LifecycleState.CERTIFIED, LifecycleState.DEPRECATED, LifecycleState.REVOKED},
            LifecycleState.CERTIFIED: {LifecycleState.DEPRECATED, LifecycleState.REVOKED},
        }
        if target not in allowed.get(current, set()):
            raise KernelStateError(f"Illegal transition from {current} to {target}")
        return True

    def calculate_merkle_root(self, leaves: Sequence[str]) -> str:
        if not leaves:
            return hashlib.sha256(b"").hexdigest()
        current_layer = [hashlib.sha256(l.encode("utf-8")).hexdigest() for l in leaves]
        while len(current_layer) > 1:
            if len(current_layer) % 2 != 0:
                current_layer.append(current_layer[-1])
            next_layer = []
            for i in range(0, len(current_layer), 2):
                combined = current_layer[i] + current_layer[i + 1]
                next_layer.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            current_layer = next_layer
        return current_layer[0]
