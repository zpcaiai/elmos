from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from .canonical import validate_digest, validate_identifier


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


TERMINAL_RUN_STATES = frozenset(
    {
        ProofRunState.SUCCEEDED,
        ProofRunState.FAILED,
        ProofRunState.CANCELLED,
        ProofRunState.TIMED_OUT,
    }
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class TrustedIdentity:
    tenant_id: str
    actor_id: str
    project_id: str | None = None
    roles: tuple[str, ...] = ()
    authorization_ref: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.tenant_id, "identity.tenantId")
        validate_identifier(self.actor_id, "identity.actorId")
        if self.project_id is not None:
            validate_identifier(self.project_id, "identity.projectId")


@dataclass(frozen=True)
class Scope:
    tenant_id: str
    account_id: str
    project_id: str | None
    source_artifact_digest: str
    target_artifact_digest: str
    environment_digest: str
    workload_key: str
    data_classification: str = "confidential"

    def __post_init__(self) -> None:
        validate_identifier(self.tenant_id, "scope.tenantId")
        validate_identifier(self.account_id, "scope.accountId")
        if self.project_id is not None:
            validate_identifier(self.project_id, "scope.projectId")
        for name, value in (
            ("sourceArtifactDigest", self.source_artifact_digest),
            ("targetArtifactDigest", self.target_artifact_digest),
            ("environmentDigest", self.environment_digest),
        ):
            validate_digest(value, f"scope.{name}")
        validate_identifier(self.workload_key, "scope.workloadKey")
        if self.data_classification not in {
            "public",
            "internal",
            "confidential",
            "restricted",
        }:
            raise ValueError("scope.dataClassification is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenantId": self.tenant_id,
            "accountId": self.account_id,
            "projectId": self.project_id,
            "sourceArtifactDigest": self.source_artifact_digest,
            "targetArtifactDigest": self.target_artifact_digest,
            "environmentDigest": self.environment_digest,
            "workloadKey": self.workload_key,
            "dataClassification": self.data_classification,
        }


@dataclass(frozen=True)
class ProofObligation:
    id: str
    criticality: Criticality
    property_kind: str
    required_assurance: AssuranceLevel
    formula_hash: str
    allow_bounded: bool = False
    required: bool = True
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_identifier(self.id, "obligation.id")
        validate_digest(self.formula_hash, "obligation.formulaHash")


@dataclass(frozen=True)
class ProofResult:
    run_id: str
    obligation_id: str
    status: ProofStatus
    assurance_level: AssuranceLevel
    engine: str
    mode: str
    assumption_hash: str
    tcb_hash: str
    formula_hash: str | None = None
    bound: dict[str, Any] | None = None
    artifact_refs: tuple[dict[str, Any], ...] = ()
    counterexample_id: str | None = None
    diagnostics: tuple[str, ...] = ()
    stale: bool = False
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        validate_identifier(self.run_id, "proofResult.runId")
        validate_identifier(self.obligation_id, "proofResult.obligationId")
        validate_digest(self.assumption_hash, "proofResult.assumptionHash")
        validate_digest(self.tcb_hash, "proofResult.tcbHash")
        if self.formula_hash is not None:
            validate_digest(self.formula_hash, "proofResult.formulaHash")
        if self.bound is not None and not isinstance(self.bound, dict):
            raise ValueError("proofResult.bound must be an object")
        if any(not isinstance(value, dict) for value in self.artifact_refs):
            raise ValueError("proofResult.artifacts must contain objects")
        if self.counterexample_id is not None:
            validate_identifier(self.counterexample_id, "proofResult.counterexampleId")
        if any(not isinstance(value, str) for value in self.diagnostics):
            raise ValueError("proofResult.diagnostics must contain strings")


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
    readiness: str = "BLOCKED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "blockingReasons": list(self.blocking_reasons),
            "advisoryReasons": list(self.advisory_reasons),
            "evaluatedCount": self.evaluated_count,
            "readiness": self.readiness,
            "certification": "NOT_CERTIFIED",
        }


@dataclass(frozen=True)
class SkillRequest:
    skill_id: str
    scope: Scope
    subject_id: str
    idempotency_key: str
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        validate_identifier(self.skill_id, "request.skillId")
        validate_identifier(self.subject_id, "request.subjectId")
        validate_identifier(self.idempotency_key, "request.idempotencyKey")


@dataclass(frozen=True)
class SkillOutcome:
    skill_id: str
    handler_id: str
    implementation_state: str
    capability_state: str
    proof_status: ProofStatus
    assurance_level: AssuranceLevel
    mode: str
    output: dict[str, Any]
    diagnostics: tuple[str, ...] = ()
    artifact_refs: tuple[dict[str, Any], ...] = ()
    external_evidence_status: str = "NOT_RUN"
    certification_status: str = "NOT_CERTIFIED"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skillId": self.skill_id,
            "handlerId": self.handler_id,
            "implementationState": self.implementation_state,
            "capabilityState": self.capability_state,
            "proofStatus": self.proof_status.value,
            "assuranceLevel": self.assurance_level.value,
            "mode": self.mode,
            "output": self.output,
            "diagnostics": list(self.diagnostics),
            "artifactRefs": list(self.artifact_refs),
            "externalEvidenceStatus": self.external_evidence_status,
            "certificationStatus": self.certification_status,
            "createdAt": self.created_at,
        }
