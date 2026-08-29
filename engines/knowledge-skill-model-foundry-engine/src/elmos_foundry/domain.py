"""Domain models, value objects, and lifecycle state machines for Elmos Foundry.

Provides typed entities for the six asset layers:
1. Knowledge Objects
2. Skill Contracts & Handlers
3. Experience Episodes
4. Dataset Items
5. Model / Adapter Releases
6. Verifiable Evidence Bundles
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Execution and Asset Lifecycle State Machines
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Core Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TenantScope:
    tenant_id: str
    project_id: str
    actor_id: str = "system"
    revision_set_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.project_id:
            raise ValueError("tenant_id and project_id are required")


@dataclass(frozen=True)
class ContentDigest:
    algorithm: str = "sha256"
    value: str = ""

    @staticmethod
    def of(data: bytes) -> "ContentDigest":
        return ContentDigest("sha256", hashlib.sha256(data).hexdigest())

    @staticmethod
    def of_json(obj: Any) -> "ContentDigest":
        canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return ContentDigest("sha256", hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    def __str__(self) -> str:
        return f"{self.algorithm}:{self.value}"


@dataclass(frozen=True)
class ArtifactReference:
    path: str
    content_type: str
    digest: ContentDigest
    immutable: bool = True
    evidence_bound: bool = True


# ---------------------------------------------------------------------------
# Six Core Asset Entities
# ---------------------------------------------------------------------------

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
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


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
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class DatasetItem:
    item_id: str
    dataset_id: str
    tenant_id: str
    split: str  # train, val, holdout
    input_text: str
    target_text: str
    metadata: Mapping[str, Any]
    rights_class: RightsClass
    consent_status: ConsentStatus
    quality_score: float = 1.0
    quarantine: bool = False


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
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    target_id: str
    target_type: str  # skill, dataset, model, release
    gate_level: GateLevel
    verdict: str  # PASS, CONDITIONAL, FAIL
    proof_obligations: Sequence[Mapping[str, Any]]
    metrics: Mapping[str, Any]
    merkle_root: str
    signatures: Sequence[Mapping[str, Any]]
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


# ---------------------------------------------------------------------------
# Results and Responses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    operation: str
    status: str  # SUCCESS, FAILED, BLOCKED
    outputs: Mapping[str, Any]
    evidence_digest: str
    duration_ms: float
    error: str | None = None
