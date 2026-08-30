"""Immutable, bounded Foundry domain contracts and conservative evidence states."""

from __future__ import annotations

import enum
import math
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .canonical import (
    canonical_digest,
    canonical_value,
    digest_bytes,
    require_identifier,
    validate_digest,
)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class LifecycleState(str, enum.Enum):
    DRAFT = "DRAFT"
    PROFILED = "PROFILED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    EVIDENCE_SEALED = "EVIDENCE_SEALED"
    CERTIFIED = "CERTIFIED"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GateLevel(str, enum.Enum):
    E0_SYNTACTIC = "E0_SYNTACTIC"
    E1_UNIT_EVAL = "E1_UNIT_EVAL"
    E2_INTEGRATION = "E2_INTEGRATION"
    E3_SHADOW_CANARY = "E3_SHADOW_CANARY"
    E4_PRODUCTION_CERTIFIED = "E4_PRODUCTION_CERTIFIED"
    E5_FORMAL_PROVEN = "E5_FORMAL_PROVEN"


class RightsClass(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    CUSTOMER_PROPRIETARY = "customer-proprietary"


class ConsentStatus(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"


class EvidenceState(str, enum.Enum):
    NOT_RUN = "NOT_RUN"
    COLLECTED_SELF_ATTESTED = "COLLECTED_SELF_ATTESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED = "REJECTED"
    VERIFIED_INDEPENDENT = "VERIFIED_INDEPENDENT"


class CertificationStatus(str, enum.Enum):
    NOT_CERTIFIED = "NOT_CERTIFIED"
    EXTERNAL_DECISION_REQUIRED = "EXTERNAL_DECISION_REQUIRED"
    CERTIFIED = "CERTIFIED"


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Identity plus optional host-minted invocation/capability bindings.

    Direct construction intentionally produces an unauthenticated data value.
    Only ``ExecutionKernel.mint_context`` creates an accepted authority object.
    """

    tenant_id: str
    project_id: str
    actor_id: str = ""
    revision_set_id: str = ""
    environment_id: str = ""
    workspace_digest: str = ""
    purpose: str = ""
    invocation_id: str = ""
    lease_id: str = ""
    capabilities: tuple[str, ...] = ()
    issued_at: int = 0
    expires_at: int = 0
    mint_authority: str = ""
    authentication_tag: str = ""
    authenticated: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.tenant_id, "tenant_id")
        require_identifier(self.project_id, "project_id")
        for name in (
            "actor_id",
            "environment_id",
            "purpose",
            "invocation_id",
            "lease_id",
            "mint_authority",
        ):
            value = getattr(self, name)
            if value:
                require_identifier(value, name)
        if self.workspace_digest:
            validate_digest(self.workspace_digest, "workspace_digest")
        if self.revision_set_id:
            validate_digest(self.revision_set_id, "revision_set_id")
        canonical_capabilities = tuple(sorted(set(self.capabilities)))
        if canonical_capabilities != tuple(self.capabilities):
            raise ValueError("capabilities must be unique and canonically sorted")
        for capability in self.capabilities:
            require_identifier(capability, "capability")
        for name in ("issued_at", "expires_at"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.authenticated:
            self.require_complete()
            validate_digest(self.authentication_tag, "authentication_tag")

    def require_complete(self) -> None:
        names = (
            "actor_id",
            "environment_id",
            "workspace_digest",
            "revision_set_id",
            "purpose",
            "invocation_id",
            "lease_id",
            "mint_authority",
        )
        missing = [name for name in names if not getattr(self, name)]
        if missing:
            raise ValueError(f"security context is incomplete: {missing}")
        if not self.capabilities:
            raise ValueError("security context has no leased capabilities")
        if self.issued_at <= 0 or self.expires_at <= self.issued_at:
            raise ValueError("security context lease interval is invalid")

    def binding_document(self) -> dict[str, Any]:
        return {
            "schema_version": "elmos.foundry.security-context.v1",
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "environment_id": self.environment_id,
            "workspace_digest": self.workspace_digest,
            "revision_set_id": self.revision_set_id,
            "purpose": self.purpose,
            "invocation_id": self.invocation_id,
            "lease_id": self.lease_id,
            "capabilities": list(self.capabilities),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "mint_authority": self.mint_authority,
        }

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self.binding_document())


@dataclass(frozen=True, slots=True)
class ContentDigest:
    algorithm: str = "sha256"
    value: str = ""

    def __post_init__(self) -> None:
        if (
            self.algorithm != "sha256"
            or len(self.value) != 64
            or any(char not in "0123456789abcdef" for char in self.value)
        ):
            raise ValueError("content digest must be sha256 with 64 lowercase hex digits")

    @staticmethod
    def of(data: bytes) -> "ContentDigest":
        return ContentDigest("sha256", digest_bytes(data).removeprefix("sha256:"))

    @staticmethod
    def of_json(obj: Any) -> "ContentDigest":
        return ContentDigest("sha256", canonical_digest(obj).removeprefix("sha256:"))

    @staticmethod
    def parse(value: str) -> "ContentDigest":
        validate_digest(value)
        return ContentDigest("sha256", value.removeprefix("sha256:"))

    def __str__(self) -> str:
        return f"sha256:{self.value}"


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    path: str
    content_type: str
    digest: ContentDigest
    immutable: bool = True
    evidence_bound: bool = True

    def __post_init__(self) -> None:
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("artifact path must be a safe relative path")
        if not self.content_type or len(self.content_type.encode("utf-8")) > 256:
            raise ValueError("content_type must be bounded")


@dataclass(frozen=True)
class KnowledgeObject:
    object_id: str
    tenant_id: str
    source_id: str
    object_type: str
    content_hash: str
    confidentiality: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    rights_class: RightsClass = RightsClass.INTERNAL
    training_consent: ConsentStatus = ConsentStatus.DENY
    quality_score: float = 1.0
    created_at: str = field(default_factory=_utc_now)
    project_id: str = ""
    evidence_state: EvidenceState = EvidenceState.NOT_RUN
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED

    def __post_init__(self) -> None:
        if not math.isfinite(self.quality_score) or not 0 <= self.quality_score <= 1:
            raise ValueError("quality_score must be finite and in [0, 1]")
        canonical_value(self.payload)
        canonical_value(self.provenance)


@dataclass(frozen=True)
class SkillContract:
    skill_name: str
    pack: str
    owner: str
    risk_class: str
    status: LifecycleState
    version: str
    content_hash: str
    preconditions: Sequence[str] = field(default_factory=list)
    postconditions: Sequence[str] = field(default_factory=list)
    inputs_schema: Mapping[str, Any] = field(default_factory=dict)
    outputs_schema: Mapping[str, Any] = field(default_factory=dict)
    rollback_policy: Mapping[str, Any] = field(default_factory=dict)
    evidence_state: EvidenceState = EvidenceState.NOT_RUN
    external_evidence_status: str = "NOT_RUN"
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED

    def __post_init__(self) -> None:
        require_identifier(self.skill_name, "skill_name")
        canonical_value(self.inputs_schema)
        canonical_value(self.outputs_schema)
        canonical_value(self.rollback_policy)


@dataclass(frozen=True)
class ExperienceEpisode:
    episode_id: str
    tenant_id: str
    project_id: str
    release_id: str
    task_type: str
    task_goal: str
    trajectory: Sequence[Mapping[str, Any]]
    outcome: Mapping[str, Any]
    reward_score: float
    verifier_evidence: Mapping[str, Any]
    created_at: str = field(default_factory=_utc_now)
    evidence_state: EvidenceState = EvidenceState.NOT_RUN
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED

    def __post_init__(self) -> None:
        if not math.isfinite(self.reward_score) or not 0 <= self.reward_score <= 1:
            raise ValueError("reward_score must be finite and in [0, 1]")
        canonical_value(self.trajectory)
        canonical_value(self.outcome)
        canonical_value(self.verifier_evidence)


@dataclass(frozen=True)
class DatasetItem:
    item_id: str
    dataset_id: str
    tenant_id: str
    split: str
    input_text: str
    target_text: str
    metadata: Mapping[str, Any]
    rights_class: RightsClass
    consent_status: ConsentStatus
    quality_score: float = 1.0
    quarantine: bool = False
    project_id: str = ""
    evidence_state: EvidenceState = EvidenceState.NOT_RUN
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED

    def __post_init__(self) -> None:
        if self.split not in {"train", "val", "validation", "holdout", "test"}:
            raise ValueError("dataset split is not recognized")
        if not math.isfinite(self.quality_score) or not 0 <= self.quality_score <= 1:
            raise ValueError("quality_score must be finite and in [0, 1]")
        canonical_value(self.metadata)


@dataclass(frozen=True)
class ModelRelease:
    release_id: str
    base_model: str
    adapter_name: str
    version: str
    tenant_id: str
    weights_digest: ContentDigest
    skill_set: Sequence[str]
    knowledge_snapshot_digest: str
    policy_bundle_digest: str
    gate_level: GateLevel
    status: LifecycleState
    created_at: str = field(default_factory=_utc_now)
    project_id: str = ""
    evidence_state: EvidenceState = EvidenceState.NOT_RUN
    external_evidence_status: str = "NOT_RUN"
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    target_id: str
    target_type: str
    gate_level: GateLevel
    verdict: str
    proof_obligations: Sequence[Mapping[str, Any]]
    metrics: Mapping[str, Any]
    merkle_root: str
    signatures: Sequence[Mapping[str, Any]]
    created_at: str = field(default_factory=_utc_now)
    tenant_id: str = ""
    project_id: str = ""
    context_digest: str = ""
    bundle_digest: str = ""
    evidence_state: EvidenceState = EvidenceState.COLLECTED_SELF_ATTESTED
    external_evidence_status: str = "NOT_RUN"
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED
    independent_verifier: bool = False

    def __post_init__(self) -> None:
        if self.verdict not in {"PASS", "FAIL", "INCONCLUSIVE", "CONDITIONAL"}:
            raise ValueError("evidence verdict is not recognized")
        for name in ("merkle_root", "context_digest", "bundle_digest"):
            value = getattr(self, name)
            if value:
                validate_digest(value, name)
        canonical_value(self.proof_obligations)
        canonical_value(self.metrics)
        canonical_value(self.signatures)


@dataclass(frozen=True)
class ExecutionResult:
    operation: str
    status: str
    outputs: Mapping[str, Any]
    evidence_digest: str
    duration_ms: float
    error: str | None = None
    evidence_state: EvidenceState = EvidenceState.COLLECTED_SELF_ATTESTED
    external_evidence_status: str = "NOT_RUN"
    certification_status: CertificationStatus = CertificationStatus.NOT_CERTIFIED
    external_effects_performed: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.operation, "operation")
        if self.status not in {"SUCCESS", "FAILED", "BLOCKED", "IN_PROGRESS"}:
            raise ValueError("execution status is not recognized")
        validate_digest(self.evidence_digest, "evidence_digest")
        if not math.isfinite(self.duration_ms) or self.duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")
        canonical_value(self.outputs)
        if self.certification_status is CertificationStatus.CERTIFIED:
            raise ValueError("local ExecutionResult cannot claim certification")


__all__ = [
    "ArtifactReference",
    "CertificationStatus",
    "ConsentStatus",
    "ContentDigest",
    "DatasetItem",
    "EvidenceBundle",
    "EvidenceState",
    "ExecutionResult",
    "ExperienceEpisode",
    "GateLevel",
    "KnowledgeObject",
    "LifecycleState",
    "ModelRelease",
    "RightsClass",
    "SkillContract",
    "TenantScope",
]
