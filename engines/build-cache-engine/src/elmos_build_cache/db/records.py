"""Row records. Plain dataclasses so the store stays dialect-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..enums import (
    ArtifactStorageState,
    CacheEntryStatus,
    CheckpointStatus,
    FileClass,
    NodeStatus,
    Ownership,
    RunStatus,
    SecretScanStatus,
    StagedFileStatus,
    TrustNamespace,
    ValidationLevel,
)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    tenant_id: str
    project_id: str
    snapshot_id: str
    pipeline_version: str
    status: RunStatus
    version: int
    journal_sequence: int
    trust_namespace: TrustNamespace = TrustNamespace.BRANCH
    source_profile: dict[str, Any] = field(default_factory=dict)
    target_profile: dict[str, Any] = field(default_factory=dict)
    published_tree_digest: str | None = None
    evidence_bundle_digest: str | None = None


@dataclass(frozen=True)
class NodeRecord:
    run_id: str
    node_id: str
    attempt: int
    stage_id: str
    stage_version: str
    status: NodeStatus
    version: int
    lease_id: str | None = None
    lease_epoch: int = 0
    lease_expires_at: float | None = None
    heartbeat_at: float | None = None
    retries: int = 0
    retry_budget: int = 3
    action_key: str | None = None
    outcome: str | None = None
    error_code: str | None = None
    error_details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ArtifactRecord:
    tenant_id: str
    digest: str
    size_bytes: int
    media_type: str
    artifact_kind: str
    storage_state: ArtifactStorageState
    validation_level: ValidationLevel
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionCacheRecord:
    tenant_id: str
    trust_namespace: TrustNamespace
    action_key: str
    result_manifest_digest: str
    validation_level: ValidationLevel
    producer_identity: str
    provenance_digest: str
    status: CacheEntryStatus
    entry_kind: str = "POSITIVE"
    failure_code: str | None = None
    expires_at: float | None = None
    hit_count: int = 0
    saved_cpu_ms: int = 0
    saved_wall_ms: int = 0
    saved_compiler_ms: int = 0
    saved_model_tokens: int = 0
    quarantine_reason: str | None = None


@dataclass(frozen=True)
class StagedFileRecord:
    staged_file_id: str
    tenant_id: str
    project_id: str
    run_id: str
    node_id: str
    attempt: int
    logical_path: str
    file_class: FileClass
    status: StagedFileStatus
    lease_epoch: int
    version: int
    overwrite_policy: str = "reject"
    ownership: Ownership = Ownership.GENERATED
    internal_temp_path: str | None = None
    internal_sealed_path: str | None = None
    lease_id: str | None = None
    expected_size: int | None = None
    actual_size: int | None = None
    digest: str | None = None
    media_type: str | None = None
    artifact_kind: str | None = None
    action_key: str | None = None
    artifact_digest: str | None = None
    source_map_digest: str | None = None
    mode: int = 0o644
    validation_level: ValidationLevel = ValidationLevel.UNVERIFIED
    secret_scan_status: SecretScanStatus = SecretScanStatus.NOT_RUN
    quarantine_reason: str | None = None


@dataclass(frozen=True)
class CheckpointRecord:
    checkpoint_id: str
    tenant_id: str
    project_id: str
    run_id: str
    node_id: str
    attempt: int
    sequence: int
    lease_epoch: int
    manifest_digest: str
    journal_sequence: int
    status: CheckpointStatus
