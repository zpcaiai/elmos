"""Host authority, short-lived capability leases and lifecycle invariants."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import contextvars
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import threading
import time
from typing import Any

from .canonical import canonical_json_bytes, require_identifier
from .domain import LifecycleState, TenantScope


class KernelSecurityError(RuntimeError):
    """An operation lacks a valid host-minted capability context."""


class KernelStateError(RuntimeError):
    """A state transition or transaction operation is illegal."""


class RollbackError(RuntimeError):
    def __init__(self, failures: tuple[BaseException, ...]) -> None:
        self.failures = failures
        super().__init__(
            f"rollback failed in {len(failures)} action(s): "
            + ",".join(type(item).__name__ for item in failures)
        )


@dataclass(slots=True)
class _RollbackStack:
    actions: list[Callable[[], None]]


class HostContextAuthority:
    """Process-local context authority; its HMAC is not an external signature."""

    def __init__(
        self,
        *,
        authority_id: str | None = None,
        secret: bytes | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.authority_id = require_identifier(
            authority_id or f"foundry-host-{secrets.token_hex(8)}", "authority_id"
        )
        material = secrets.token_bytes(32) if secret is None else secret
        if not isinstance(material, bytes) or len(material) < 32:
            raise ValueError("host authority secret must contain at least 32 bytes")
        self.__secret = bytes(material)
        self._clock = clock

    def _tag(self, context: TenantScope) -> str:
        return (
            "sha256:"
            + hmac.new(
                self.__secret, canonical_json_bytes(context.binding_document()), hashlib.sha256
            ).hexdigest()
        )

    def mint(
        self,
        *,
        tenant_id: str,
        project_id: str,
        actor_id: str,
        environment_id: str,
        workspace_digest: str,
        revision_set_id: str,
        purpose: str,
        capabilities: Sequence[str],
        ttl_seconds: int,
        invocation_id: str | None = None,
        lease_id: str | None = None,
    ) -> TenantScope:
        if (
            not isinstance(ttl_seconds, int)
            or isinstance(ttl_seconds, bool)
            or not 1 <= ttl_seconds <= 3600
        ):
            raise KernelSecurityError("capability lease TTL must be in [1, 3600]")
        granted = tuple(sorted(set(capabilities)))
        if not granted or len(granted) > 64:
            raise KernelSecurityError("capability lease must contain 1..64 capabilities")
        issued_at = int(self._clock())
        unsigned = TenantScope(
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=actor_id,
            revision_set_id=revision_set_id,
            environment_id=environment_id,
            workspace_digest=workspace_digest,
            purpose=purpose,
            invocation_id=invocation_id or f"inv-{secrets.token_hex(16)}",
            lease_id=lease_id or f"lease-{secrets.token_hex(16)}",
            capabilities=granted,
            issued_at=issued_at,
            expires_at=issued_at + ttl_seconds,
            mint_authority=self.authority_id,
        )
        return TenantScope(
            tenant_id=unsigned.tenant_id,
            project_id=unsigned.project_id,
            actor_id=unsigned.actor_id,
            revision_set_id=unsigned.revision_set_id,
            environment_id=unsigned.environment_id,
            workspace_digest=unsigned.workspace_digest,
            purpose=unsigned.purpose,
            invocation_id=unsigned.invocation_id,
            lease_id=unsigned.lease_id,
            capabilities=unsigned.capabilities,
            issued_at=unsigned.issued_at,
            expires_at=unsigned.expires_at,
            mint_authority=unsigned.mint_authority,
            authentication_tag=self._tag(unsigned),
            authenticated=True,
        )

    def verify(self, context: TenantScope, *, now: int | None = None) -> None:
        if not isinstance(context, TenantScope) or not context.authenticated:
            raise KernelSecurityError("context is not host authenticated")
        try:
            context.require_complete()
        except ValueError as exc:
            raise KernelSecurityError("host context is incomplete") from exc
        if context.mint_authority != self.authority_id:
            raise KernelSecurityError("context was minted by a different authority")
        if not hmac.compare_digest(self._tag(context), context.authentication_tag):
            raise KernelSecurityError("context authentication tag is invalid")
        observed = int(self._clock()) if now is None else now
        if context.issued_at > observed + 5:
            raise KernelSecurityError("context lease was issued in the future")
        if observed >= context.expires_at:
            raise KernelSecurityError("context capability lease has expired")


_current_scope: contextvars.ContextVar[TenantScope | None] = contextvars.ContextVar(
    "_elmos_foundry_security_context", default=None
)


class ExecutionKernel:
    def __init__(
        self,
        authority: HostContextAuthority | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.authority = authority or HostContextAuthority(clock=clock)
        self._clock = clock
        self._active_rollbacks: dict[str, _RollbackStack] = {}
        self._revoked_leases: set[str] = set()
        self._lock = threading.RLock()

    def mint_context(self, **values: Any) -> TenantScope:
        return self.authority.mint(**values)

    def revoke_lease(self, lease_id: str) -> None:
        require_identifier(lease_id, "lease_id")
        with self._lock:
            self._revoked_leases.add(lease_id)

    def require_context(self, context: TenantScope, capability: str | None = None) -> TenantScope:
        self.authority.verify(context, now=int(self._clock()))
        with self._lock:
            if context.lease_id in self._revoked_leases:
                raise KernelSecurityError("context capability lease is revoked")
        if capability is not None:
            require_identifier(capability, "capability")
            if capability not in context.capabilities:
                raise KernelSecurityError(f"context lease does not grant capability: {capability}")
        return context

    def set_tenant_context(
        self, scope: TenantScope, *, capability: str | None = None
    ) -> contextvars.Token[TenantScope | None]:
        return _current_scope.set(self.require_context(scope, capability))

    def reset_tenant_context(self, token: contextvars.Token[TenantScope | None]) -> None:
        _current_scope.reset(token)

    @contextmanager
    def use_context(
        self, scope: TenantScope, *, capability: str | None = None
    ) -> Iterator[TenantScope]:
        token = self.set_tenant_context(scope, capability=capability)
        try:
            yield scope
        finally:
            self.reset_tenant_context(token)

    @property
    def current_tenant(self) -> TenantScope:
        scope = _current_scope.get()
        if scope is None:
            raise KernelSecurityError("fail-closed: operation requires a host-minted TenantScope")
        return self.require_context(scope)

    def register_rollback(self, transaction_id: str, action: Callable[[], None]) -> None:
        require_identifier(transaction_id, "transaction_id")
        if not callable(action):
            raise TypeError("rollback action must be callable")
        with self._lock:
            stack = self._active_rollbacks.setdefault(transaction_id, _RollbackStack([]))
            if len(stack.actions) >= 1024:
                raise KernelStateError("rollback action limit exceeded")
            stack.actions.append(action)

    def execute_rollback(self, transaction_id: str) -> None:
        require_identifier(transaction_id, "transaction_id")
        with self._lock:
            stack = self._active_rollbacks.pop(transaction_id, None)
        if stack is None:
            raise KernelStateError("unknown rollback transaction")
        failures: list[BaseException] = []
        for action in reversed(stack.actions):
            try:
                action()
            except BaseException as exc:
                failures.append(exc)
        if failures:
            raise RollbackError(tuple(failures))

    def commit_transaction(self, transaction_id: str) -> None:
        require_identifier(transaction_id, "transaction_id")
        with self._lock:
            if self._active_rollbacks.pop(transaction_id, None) is None:
                raise KernelStateError("unknown rollback transaction")

    def validate_transition(self, current: LifecycleState, target: LifecycleState) -> bool:
        if target is LifecycleState.CERTIFIED:
            raise KernelStateError("local runtime cannot transition an artifact to CERTIFIED")
        allowed = {
            LifecycleState.DRAFT: {
                LifecycleState.PROFILED,
                LifecycleState.BLOCKED,
                LifecycleState.FAILED,
                LifecycleState.CANCELLED,
            },
            LifecycleState.PROFILED: {
                LifecycleState.PLANNED,
                LifecycleState.BLOCKED,
                LifecycleState.FAILED,
                LifecycleState.CANCELLED,
            },
            LifecycleState.PLANNED: {
                LifecycleState.RUNNING,
                LifecycleState.BLOCKED,
                LifecycleState.FAILED,
                LifecycleState.CANCELLED,
            },
            LifecycleState.RUNNING: {
                LifecycleState.VERIFYING,
                LifecycleState.BLOCKED,
                LifecycleState.FAILED,
                LifecycleState.CANCELLED,
            },
            LifecycleState.VERIFYING: {
                LifecycleState.EVIDENCE_SEALED,
                LifecycleState.BLOCKED,
                LifecycleState.FAILED,
            },
            LifecycleState.EVIDENCE_SEALED: {LifecycleState.DEPRECATED, LifecycleState.REVOKED},
            LifecycleState.CERTIFIED: {LifecycleState.DEPRECATED, LifecycleState.REVOKED},
        }
        if target not in allowed.get(current, set()):
            raise KernelStateError(f"illegal transition from {current} to {target}")
        return True

    def calculate_merkle_root(self, leaves: Sequence[str]) -> str:
        if len(leaves) > 100_000:
            raise KernelStateError("Merkle leaf count exceeds local limit")
        if not leaves:
            return hashlib.sha256(b"elmos.foundry.merkle.v1\0empty").hexdigest()
        layer = [
            hashlib.sha256(
                b"elmos.foundry.merkle.v1\0leaf\0"
                + canonical_json_bytes({"index": i, "value": item})
            ).digest()
            for i, item in enumerate(leaves)
        ]
        while len(layer) > 1:
            if len(layer) % 2:
                layer.append(layer[-1])
            layer = [
                hashlib.sha256(
                    b"elmos.foundry.merkle.v1\0node\0" + layer[i] + layer[i + 1]
                ).digest()
                for i in range(0, len(layer), 2)
            ]
        return layer[0].hex()


__all__ = [
    "ExecutionKernel",
    "HostContextAuthority",
    "KernelSecurityError",
    "KernelStateError",
    "RollbackError",
]
