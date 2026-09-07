from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

class ProofStatus(StrEnum):
    PROVED_CERTIFIED = "PROVED_CERTIFIED"
    PROVED_INDUCTIVE = "PROVED_INDUCTIVE"
    PROVED_SOLVER_TRUSTED = "PROVED_SOLVER_TRUSTED"
    PROVED_FOR_SUPPORTED_FRAGMENT = "PROVED_FOR_SUPPORTED_FRAGMENT"
    BOUNDED_NO_COUNTEREXAMPLE = "BOUNDED_NO_COUNTEREXAMPLE"
    REFUTED_WITH_COUNTEREXAMPLE = "REFUTED_WITH_COUNTEREXAMPLE"
    UNKNOWN_TIMEOUT = "UNKNOWN_TIMEOUT"
    UNKNOWN_RESOURCE_LIMIT = "UNKNOWN_RESOURCE_LIMIT"
    UNSUPPORTED = "UNSUPPORTED"
    ASSUMPTION_REQUIRED = "ASSUMPTION_REQUIRED"
    RUNTIME_MONITORED = "RUNTIME_MONITORED"
    WAIVED_BY_APPROVER = "WAIVED_BY_APPROVER"

class AssuranceLevel(StrEnum):
    NONE = "NONE"
    A0_TESTED = "A0_TESTED"
    A1_BOUNDED = "A1_BOUNDED"
    A2_SOLVER_PROVED = "A2_SOLVER_PROVED"
    A3_CERTIFIED = "A3_CERTIFIED"
    A4_COMPOSED = "A4_COMPOSED"
    TRUSTED = "TRUSTED"

class Criticality(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"

class ProofRunState(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"

TERMINAL_STATES = {
    ProofRunState.SUCCEEDED, ProofRunState.FAILED,
    ProofRunState.CANCELLED, ProofRunState.TIMED_OUT,
}

@dataclass(frozen=True)
class ProofObligation:
    id: str
    criticality: Criticality
    property_kind: str
    required_assurance: AssuranceLevel
    allow_bounded: bool = False
    required: bool = True
    dependencies: tuple[str, ...] = ()

@dataclass(frozen=True)
class ProofResult:
    obligation_id: str
    status: ProofStatus
    assurance_level: AssuranceLevel
    mode: str
    stale: bool = False
    bound: dict[str, Any] | None = None
    diagnostics: tuple[str, ...] = ()

@dataclass(frozen=True)
class Waiver:
    obligation_id: str
    status: str
    risk: str
    approvals: tuple[str, ...]
    compensating_controls: tuple[str, ...]
    expires_at: str

@dataclass(frozen=True)
class GateDecision:
    decision: str
    blocking_reasons: tuple[str, ...] = ()
    advisory_reasons: tuple[str, ...] = ()
    evaluated_count: int = 0

@dataclass
class ProofRun:
    id: str
    account_id: str
    obligation_id: str
    state: ProofRunState = ProofRunState.QUEUED
    owner_id: str | None = None
    fencing_token: int = 1
    result: ProofResult | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
