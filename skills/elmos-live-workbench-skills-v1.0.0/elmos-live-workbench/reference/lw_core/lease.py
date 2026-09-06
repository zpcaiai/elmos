"""Fixed-window model using an injected, trusted server clock. No provider is started.
Production adapters MUST verify signatures, use durable compare-and-swap, a local
monotonic deadline, cross-process authorization and an independent provider TTL.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math

class LeaseError(ValueError): pass

@dataclass(frozen=True)
class ReadinessProof:
    proof_id: str
    tenant: str
    revision: str
    session_id: str
    generation: int
    verifier: str
    committed: bool
    smoke_passed: bool

@dataclass
class PreviewLease:
    tenant: str
    revision: str
    session_id: str
    generation: int
    created_at: float
    provider_deadline: float
    trusted_verifiers: frozenset[str] = frozenset({"independent-smoke-verifier"})
    window_seconds: int = field(default=600, init=False)
    cleanup_seconds: int = field(default=30, init=False)
    prepare_seconds: int = field(default=600, init=False)
    ready_at: float | None = field(default=None, init=False)
    expires_at: float | None = field(default=None, init=False)
    state: str = field(default="preparing", init=False)
    runtime_status: str = field(default="not-started", init=False)
    proof_id: str | None = field(default=None, init=False)
    _last_time: float = field(default=0, init=False)

    def __post_init__(self):
        if not math.isfinite(self.created_at) or not math.isfinite(self.provider_deadline) or self.created_at < 0:
            raise LeaseError("invalid server time")
        self._last_time = self.created_at
        if self.provider_deadline < self.created_at + 600 + 30:
            raise LeaseError("provider cannot cover even the minimum window")

    def _clock(self, now: float) -> None:
        if not math.isfinite(now) or now < self._last_time:
            raise LeaseError("clock regression; fail closed")
        self._last_time = now

    def mark_ready(self, now: float, proof: ReadinessProof) -> float:
        self._clock(now)
        if (proof.tenant,proof.revision,proof.session_id,proof.generation) != (self.tenant,self.revision,self.session_id,self.generation):
            raise LeaseError("readiness binding mismatch")
        if proof.verifier not in self.trusted_verifiers or not proof.committed or not proof.smoke_passed:
            raise LeaseError("readiness evidence not accepted")
        if self.ready_at is not None:
            if proof.proof_id != self.proof_id:
                raise LeaseError("different readiness evidence for an already started window")
            if self.state != "ready" or now >= self.expires_at:
                raise LeaseError("window no longer active")
            return self.expires_at
        if self.state != "preparing" or now >= self.created_at + self.prepare_seconds:
            raise LeaseError("prepare budget exhausted or invalid state")
        if self.provider_deadline < now + self.window_seconds + self.cleanup_seconds:
            raise LeaseError("insufficient provider remaining lifetime")
        self.ready_at = now
        self.expires_at = now + self.window_seconds
        self.proof_id = proof.proof_id
        self.state = "ready"
        self.runtime_status = "running"
        return self.expires_at

    def authorize(self, now: float, tenant: str, generation: int) -> None:
        self._clock(now)
        if tenant != self.tenant or generation != self.generation:
            raise LeaseError("tenant or fencing mismatch")
        if self.state != "ready" or self.expires_at is None:
            raise LeaseError("not active")
        if now >= self.expires_at:
            self.state = "expiring"
            raise LeaseError("expired")

    def set_runtime_status(self, now: float, status: str) -> None:
        self.authorize(now,self.tenant,self.generation)
        if status not in {"running","paused","degraded"}:
            raise LeaseError("invalid runtime status")
        self.runtime_status = status

    def replace_worker(self, now: float) -> int:
        self.authorize(now,self.tenant,self.generation)
        self.generation += 1
        self.runtime_status = "degraded"
        return self.generation

    def close(self, now: float, observed_checks: dict[str,bool]) -> str:
        self._clock(now)
        self.state = "expiring"
        required = {"proxy_revoked","connections_closed","processes_stopped","volumes_deleted","secrets_revoked","adapters_stopped","ports_closed"}
        # Caller must supply authenticated *observations*, not planned cleanup operations.
        ok = set(observed_checks) == required and all(v is True for v in observed_checks.values())
        self.state = "closed" if ok else "quarantined"
        if observed_checks.get("processes_stopped") is True:
            self.runtime_status = "stopped"
        return self.state
