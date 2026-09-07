"""Versioned domain contracts for durable multimodal intake."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import normalize_sha256, require_actor_id, require_resource_id
from .errors import ValidationError


UNTRUSTED_CONTENT = "UNTRUSTED_CONTENT"


class SessionStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    PARTIAL_READY = "PARTIAL_READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AssetStatus(StrEnum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class UploadStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"
    QUARANTINED = "QUARANTINED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ResultStatus(StrEnum):
    PASSED = "PASSED"
    PARTIAL = "PARTIAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class AssetKind(StrEnum):
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"
    LOG = "LOG"
    DOCX = "DOCX"
    PDF = "PDF"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    ARCHIVE = "ARCHIVE"
    UNKNOWN = "UNKNOWN"


class ContentBlockKind(StrEnum):
    TEXT = "TEXT"
    HEADING = "HEADING"
    CODE = "CODE"
    LOG = "LOG"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    AUDIO_SEGMENT = "AUDIO_SEGMENT"
    PAGE = "PAGE"
    REVIEW_NOTE = "REVIEW_NOTE"


class SecurityDecision(StrEnum):
    ALLOW = "ALLOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    QUARANTINE = "QUARANTINE"


class ReviewTargetKind(StrEnum):
    TEXT = "TEXT"
    SPEAKER = "SPEAKER"
    TIME_RANGE = "TIME_RANGE"
    BBOX = "BBOX"
    TABLE = "TABLE"
    REQUIREMENT = "REQUIREMENT"
    CONFLICT = "CONFLICT"


class ReviewTaskState(StrEnum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REOPENED = "REOPENED"
    REVERTING = "REVERTING"
    REVERTED = "REVERTED"


class ReviewDecisionAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REOPEN = "REOPEN"
    REVERT = "REVERT"


class ReviewPropagationState(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ReviewPropagationDirection(StrEnum):
    APPLY = "APPLY"
    REVERT = "REVERT"


class ReviewHeadReservationState(StrEnum):
    """Durable ownership state for one exact authoritative target-head version."""

    PROPAGATING = "PROPAGATING"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"
    APPLIED = "APPLIED"
    REVERTED = "REVERTED"


class GovernanceDeletionJobState(StrEnum):
    """Persistent Skill 27 state; UNKNOWN never counts as deletion proof."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


class GovernanceDeletionCommandState(StrEnum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    UNKNOWN = "UNKNOWN"
    VERIFIED = "VERIFIED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: str
    project_id: str
    actor_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", require_resource_id(self.tenant_id, "tenant_id"))
        object.__setattr__(self, "project_id", require_resource_id(self.project_id, "project_id"))
        object.__setattr__(self, "actor_id", require_actor_id(self.actor_id))


@dataclass(frozen=True, slots=True)
class InputSession:
    session_id: str
    tenant_id: str
    project_id: str
    created_by: str
    requested_role: str
    status: SessionStatus
    idempotency_key: str
    trace_id: str
    version: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class InputAsset:
    asset_id: str
    session_id: str
    tenant_id: str
    project_id: str
    display_name: str
    declared_media_type: str
    detected_media_type: str | None
    kind: AssetKind
    byte_size: int
    sha256: str | None
    cas_digest: str | None
    status: AssetStatus
    security_decision: SecurityDecision | None
    version: int
    created_at: str
    updated_at: str
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class UploadSession:
    upload_id: str
    asset_id: str
    tenant_id: str
    project_id: str
    idempotency_key: str
    request_digest: str
    expected_size: int
    expected_sha256: str
    part_size: int
    status: UploadStatus
    received_bytes: int
    commit_idempotency_key: str | None
    expires_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PartAck:
    upload_id: str
    part_number: int
    status: str
    received_bytes: int
    next_offset: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    anchor_id: str
    asset_id: str
    source_sha256: str
    locator_type: str
    page_number: int | None = None
    paragraph_index: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    time_start_ms: int | None = None
    time_end_ms: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    symbol: str | None = None
    excerpt_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "anchor_id", require_resource_id(self.anchor_id, "anchor_id"))
        object.__setattr__(self, "asset_id", require_resource_id(self.asset_id, "asset_id"))
        object.__setattr__(self, "source_sha256", normalize_sha256(self.source_sha256))
        if self.excerpt_sha256 is not None:
            object.__setattr__(self, "excerpt_sha256", normalize_sha256(self.excerpt_sha256))
        if not self.locator_type:
            raise ValidationError("SOURCE_ANCHOR_LOCATOR_REQUIRED")
        if self.page_number is not None and self.page_number < 1:
            raise ValidationError("SOURCE_ANCHOR_PAGE_INVALID")
        if self.paragraph_index is not None and self.paragraph_index < 0:
            raise ValidationError("SOURCE_ANCHOR_PARAGRAPH_INVALID")
        if self.line_start is not None and self.line_start < 1:
            raise ValidationError("SOURCE_ANCHOR_LINE_INVALID")
        if self.line_end is not None and (self.line_start is None or self.line_end < self.line_start):
            raise ValidationError("SOURCE_ANCHOR_LINE_RANGE_INVALID")
        if self.time_start_ms is not None and self.time_start_ms < 0:
            raise ValidationError("SOURCE_ANCHOR_TIME_INVALID")
        if self.time_end_ms is not None and (
            self.time_start_ms is None or self.time_end_ms < self.time_start_ms
        ):
            raise ValidationError("SOURCE_ANCHOR_TIME_RANGE_INVALID")
        if self.bbox is not None and (
            len(self.bbox) != 4
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value < 0
                for value in self.bbox
            )
        ):
            raise ValidationError("SOURCE_ANCHOR_BBOX_INVALID")
        if self.bbox is not None:
            object.__setattr__(self, "bbox", tuple(float(value) for value in self.bbox))


@dataclass(frozen=True, slots=True)
class ContentBlock:
    block_id: str
    asset_id: str
    kind: ContentBlockKind
    ordinal: int
    text: str | None
    payload: Mapping[str, Any] = field(default_factory=dict)
    anchors: tuple[SourceAnchor, ...] = ()
    confidence: float | None = None
    schema_version: str = "1.0.0"
    trust_label: str = UNTRUSTED_CONTENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", require_resource_id(self.block_id, "block_id"))
        object.__setattr__(self, "asset_id", require_resource_id(self.asset_id, "asset_id"))
        if self.ordinal < 0:
            raise ValidationError("CONTENT_BLOCK_ORDINAL_INVALID")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("CONTENT_BLOCK_CONFIDENCE_INVALID")
        if self.trust_label != UNTRUSTED_CONTENT:
            raise ValidationError("CONTENT_BLOCK_TRUST_LABEL_INVALID")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        object.__setattr__(self, "anchors", tuple(self.anchors))


@dataclass(frozen=True, slots=True)
class DetectionResult:
    kind: AssetKind
    media_type: str
    decision: SecurityDecision
    confidence: float
    findings: tuple[str, ...] = ()
    registry_version: str = "elmos-file-types-1.0.0"
    evidence: tuple[str, ...] = ()
    parser_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValidationError("DETECTION_CONFIDENCE_INVALID")
        object.__setattr__(self, "findings", tuple(self.findings))
        if not self.registry_version:
            raise ValidationError("DETECTION_REGISTRY_VERSION_REQUIRED")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "parser_candidates", tuple(self.parser_candidates))


@dataclass(frozen=True, slots=True)
class ParseReport:
    parser: str
    status: ResultStatus
    blocks: tuple[ContentBlock, ...]
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    provider_receipt: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocks", tuple(self.blocks))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "provider_receipt", MappingProxyType(dict(self.provider_receipt)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class ProcessingJob:
    job_id: str
    tenant_id: str
    project_id: str
    session_id: str
    idempotency_key: str
    request_digest: str
    status: JobStatus
    stage: str
    attempt: int
    max_attempts: int
    result_status: ResultStatus
    failure_code: str | None
    created_at: str
    updated_at: str
    cancel_requested: bool = False
    cancel_requested_by: str | None = None
    cancel_requested_at: str | None = None
    cancel_reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    job: ProcessingJob
    session: InputSession
    assets: tuple[InputAsset, ...]
    reports: Mapping[str, ParseReport]

    def __post_init__(self) -> None:
        object.__setattr__(self, "assets", tuple(self.assets))
        object.__setattr__(self, "reports", MappingProxyType(dict(self.reports)))


@dataclass(frozen=True, slots=True)
class ReviewTask:
    task_id: str
    tenant_id: str
    project_id: str
    asset_id: str
    target_kind: ReviewTargetKind
    target: Any
    original_value: Any
    source_digest: str
    source_ref: Mapping[str, Any]
    confidence: float
    reason: str
    state: ReviewTaskState
    current_correction_version: int
    current_correction_digest: str | None
    effective_version: int
    effective_digest: str | None
    claim_actor_id: str | None
    claim_fence: int
    claim_expires_at: str | None
    version: int
    created_by: str
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class ReviewCorrection:
    correction_id: str
    tenant_id: str
    project_id: str
    task_id: str
    correction_version: int
    parent_correction_version: int
    target_kind: ReviewTargetKind
    target: Any
    original_value: Any
    corrected_value: Any
    source_digest: str
    correction_digest: str
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    decision_id: str
    tenant_id: str
    project_id: str
    task_id: str
    decision_version: int
    decision: ReviewDecisionAction
    prior_state: ReviewTaskState
    next_state: ReviewTaskState
    correction_version: int | None
    correction_digest: str | None
    source_digest: str
    actor_id: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ReviewAuditEntry:
    audit_id: str
    tenant_id: str
    project_id: str
    task_id: str
    event_type: str
    actor_id: str
    prior_state: ReviewTaskState | None
    next_state: ReviewTaskState | None
    task_version: int
    details: Mapping[str, Any]
    occurred_at: str


@dataclass(frozen=True, slots=True)
class ReviewPropagationTask:
    propagation_id: str
    tenant_id: str
    project_id: str
    task_id: str
    decision_id: str
    correction_version: int
    channel: str
    direction: ReviewPropagationDirection
    payload: Mapping[str, Any]
    state: ReviewPropagationState
    claim_capability_id: str | None
    claim_fence: int
    claim_expires_at: str | None
    dispatch_started_at: str | None
    result: Mapping[str, Any] | None
    failure_code: str | None
    reconciliation_required: bool
    version: int
    created_at: str
    updated_at: str
    completed_at: str | None
    reconciled_at: str | None


@dataclass(frozen=True, slots=True)
class ReviewEffectiveProjection:
    tenant_id: str
    project_id: str
    task_id: str
    channel: str
    source_decision_id: str
    correction_version: int
    direction: ReviewPropagationDirection
    target_kind: ReviewTargetKind
    target: Any
    effective_value: Any
    effective_value_digest: str
    source_digest: str
    version: int
    updated_at: str
