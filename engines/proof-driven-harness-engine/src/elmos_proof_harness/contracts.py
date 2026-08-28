"""Typed, JSON-serializable contracts shared by all eight runtime kernels.

The contracts intentionally carry tenant, project and actor identity at every
authoritative boundary.  Callers should use :func:`canonical.canonical_json`
or an explicit transport serializer; enums inherit from ``StrEnum`` and all
timestamps must be timezone-aware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import math
from typing import Any, Mapping

from .canonical import digest_object, freeze_json, require_sha256_digest
from .errors import ValidationError


def utc_now() -> datetime:
    return datetime.now(UTC)


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} is required", details={"field": field_name})
    if len(value) > 512:
        raise ValidationError(f"{field_name} is too long", details={"field": field_name})
    return value


def _require_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must be timezone-aware", code="INVALID_TIMESTAMP")
    return value


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProofStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
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


PROOF_STRENGTH: Mapping[ProofStatus, int] = {
    ProofStatus.BOUNDED_NO_COUNTEREXAMPLE: 1,
    ProofStatus.PROVED_FOR_SUPPORTED_FRAGMENT: 2,
    ProofStatus.PROVED_SOLVER_TRUSTED: 3,
    ProofStatus.PROVED_INDUCTIVE: 4,
    ProofStatus.PROVED_CERTIFIED: 5,
}
NON_CLOSING_PROOF_STATUSES = frozenset(status for status in ProofStatus if status not in PROOF_STRENGTH)


def proof_status_meets(actual: ProofStatus, minimum: ProofStatus) -> bool:
    """Compare only proof-bearing statuses; workflow/error states never pass."""

    actual_rank = PROOF_STRENGTH.get(actual)
    minimum_rank = PROOF_STRENGTH.get(minimum)
    return actual_rank is not None and minimum_rank is not None and actual_rank >= minimum_rank


class GateDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CertificationStatus(StrEnum):
    BLOCKED = "BLOCKED"
    FAILED_ASSURANCE = "FAILED_ASSURANCE"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"
    CERTIFIED = "CERTIFIED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class EvidenceClass(StrEnum):
    CERTIFIED_PROOF_OBJECT = "certified-proof-object"
    SOLVER_MODEL = "solver-model-result"
    COMPILER_STATIC = "compiler-static"
    DIFFERENTIAL_RUNTIME = "differential-runtime"
    PROPERTY_TEST = "property-test"
    METAMORPHIC = "metamorphic"
    FUZZ = "fuzz"
    OPERATIONAL = "operational"
    RUNTIME_MONITOR = "runtime-monitor"
    HUMAN_APPROVAL = "human-approval"
    EXTERNAL_SIGNATURE = "external-signature"
    CHECKPOINT = "checkpoint"
    AUDIT = "audit"


@dataclass(frozen=True, slots=True)
class SecurityContext:
    """Authenticated resource binding supplied to every mutable operation."""

    tenant_id: str
    project_id: str
    actor_id: str
    run_id: str | None = None
    execution_epoch: int = 1
    fencing_generation: int = 1
    authority_revision: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.tenant_id, "tenant_id")
        _require_text(self.project_id, "project_id")
        _require_text(self.actor_id, "actor_id")
        if self.run_id is not None:
            _require_text(self.run_id, "run_id")
        if self.execution_epoch < 1:
            raise ValidationError("execution_epoch must be positive")
        if self.fencing_generation < 1:
            raise ValidationError("fencing_generation must be positive")
        if self.authority_revision is not None:
            require_sha256_digest(self.authority_revision, field="authority_revision")

    def for_run(self, run_id: str, *, execution_epoch: int | None = None, fencing_generation: int | None = None) -> "SecurityContext":
        return SecurityContext(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            actor_id=self.actor_id,
            run_id=run_id,
            execution_epoch=self.execution_epoch if execution_epoch is None else execution_epoch,
            fencing_generation=self.fencing_generation if fencing_generation is None else fencing_generation,
            authority_revision=self.authority_revision,
        )


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    sha256: str
    media_type: str
    byte_length: int
    domain: str = "evidence-content"
    uri: str | None = None
    schema_version: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.artifact_id, "artifact_id")
        require_sha256_digest(self.sha256, field="sha256")
        _require_text(self.media_type, "media_type")
        _require_text(self.domain, "domain")
        if self.byte_length < 0:
            raise ValidationError("byte_length cannot be negative")


@dataclass(frozen=True, slots=True)
class EvidenceProducer:
    execution_id: str
    source: str
    tool_name: str
    tool_digest: str
    environment_revision: str
    independent: bool = False

    def __post_init__(self) -> None:
        _require_text(self.execution_id, "execution_id")
        _require_text(self.source, "source")
        _require_text(self.tool_name, "tool_name")
        require_sha256_digest(self.tool_digest, field="tool_digest")
        require_sha256_digest(self.environment_revision, field="environment_revision")


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    subject_revision: str
    kind: str
    evidence_class: str
    scope: str
    content: ArtifactRef
    producer: EvidenceProducer
    created_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    lineage: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("evidence_id", "tenant_id", "project_id", "actor_id", "kind", "evidence_class", "scope"):
            _require_text(getattr(self, name), name)
        require_sha256_digest(self.subject_revision, field="subject_revision")
        _require_aware(self.created_at, "created_at")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "expires_at")
            if self.expires_at <= self.created_at:
                raise ValidationError("expires_at must follow created_at")
        if len(set(self.lineage)) != len(self.lineage):
            raise ValidationError("evidence lineage contains duplicates")


@dataclass(frozen=True, slots=True)
class ToolIdentity:
    name: str
    version: str
    digest: str
    adapter_version: str
    encoder_digest: str

    def __post_init__(self) -> None:
        _require_text(self.name, "tool.name")
        _require_text(self.version, "tool.version")
        _require_text(self.adapter_version, "tool.adapter_version")
        require_sha256_digest(self.digest, field="tool.digest")
        require_sha256_digest(self.encoder_digest, field="tool.encoder_digest")


@dataclass(frozen=True, slots=True)
class ProofObligation:
    obligation_id: str
    tenant_id: str
    project_id: str
    graph_id: str
    goal_id: str
    subject_revision: str
    family: str
    relation: str
    scope: str
    severity: Severity
    required_minimum_status: ProofStatus
    accepted_evidence_classes: frozenset[str]
    assumptions: tuple[str, ...] = ()
    accepted_tool_digests: frozenset[str] = frozenset()
    accepted_environment_revisions: frozenset[str] = frozenset()
    open_world: bool = False
    affected_symbols: tuple[str, ...] = ()
    status: ProofStatus = ProofStatus.PENDING
    sequence: int = 0

    def __post_init__(self) -> None:
        for name in ("obligation_id", "tenant_id", "project_id", "graph_id", "goal_id", "family", "relation", "scope"):
            _require_text(getattr(self, name), name)
        require_sha256_digest(self.subject_revision, field="subject_revision")
        if self.required_minimum_status not in PROOF_STRENGTH:
            raise ValidationError("required minimum must be a proof-bearing status")
        if not self.accepted_evidence_classes:
            raise ValidationError("accepted_evidence_classes cannot be empty")
        for digest in self.accepted_tool_digests:
            require_sha256_digest(digest, field="accepted_tool_digest")
        for digest in self.accepted_environment_revisions:
            require_sha256_digest(digest, field="accepted_environment_revision")
        if self.sequence < 0:
            raise ValidationError("obligation sequence cannot be negative")


@dataclass(frozen=True, slots=True)
class ProofResult:
    result_id: str
    obligation_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    status: ProofStatus
    subject_revision: str
    scope: str
    assumptions: tuple[str, ...]
    tool: ToolIdentity
    environment_revision: str
    inputs_sha256: str
    evidence_ids: tuple[str, ...]
    evidence_classes: frozenset[str]
    created_at: datetime = field(default_factory=utc_now)
    resource_bounds: Mapping[str, int | float | str] = field(default_factory=dict)
    counterexample_evidence_id: str | None = None
    error_code: str | None = None
    independent_verifier: bool = False

    def __post_init__(self) -> None:
        for name in ("result_id", "obligation_id", "tenant_id", "project_id", "actor_id", "scope"):
            _require_text(getattr(self, name), name)
        require_sha256_digest(self.subject_revision, field="subject_revision")
        require_sha256_digest(self.environment_revision, field="environment_revision")
        require_sha256_digest(self.inputs_sha256, field="inputs_sha256")
        _require_aware(self.created_at, "created_at")
        if not self.evidence_ids:
            raise ValidationError("proof result requires evidence ids")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValidationError("proof result evidence ids contain duplicates")
        if self.status is ProofStatus.REFUTED_WITH_COUNTEREXAMPLE and not self.counterexample_evidence_id:
            raise ValidationError("refuted result requires a counterexample")


@dataclass(frozen=True, slots=True)
class RevisionSet:
    revision_set_id: str
    tenant_id: str
    project_id: str
    goal_id: str
    source_repository: str
    baseline_repository: str
    requirements: str
    policy: str
    workflow: str
    model_route: str
    toolchain: str
    environment: str
    domain_pack: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for name in ("revision_set_id", "tenant_id", "project_id", "goal_id"):
            _require_text(getattr(self, name), name)
        _require_aware(self.created_at, "created_at")
        for name, value in self.revisions().items():
            require_sha256_digest(value, field=name)

    def revisions(self) -> dict[str, str]:
        return {
            "source_repository": self.source_repository,
            "baseline_repository": self.baseline_repository,
            "requirements": self.requirements,
            "policy": self.policy,
            "workflow": self.workflow,
            "model_route": self.model_route,
            "toolchain": self.toolchain,
            "environment": self.environment,
            "domain_pack": self.domain_pack,
        }

    def is_complete(self) -> bool:
        return len(self.revisions()) == 9 and all(self.revisions().values())


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: str
    decision: GateDecision
    evidence_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.gate, "gate")
        if self.decision is GateDecision.PASS and not self.evidence_ids:
            raise ValidationError("passing gate requires immutable evidence ids", code="GATE_EVIDENCE_REQUIRED")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValidationError("gate evidence ids contain duplicates")


@dataclass(frozen=True, slots=True)
class ProofDecision:
    obligation_id: str
    result_id: str
    accepted: bool
    closed: bool
    applied_status: ProofStatus
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompletionCertificate:
    certificate_id: str
    tenant_id: str
    project_id: str
    goal_id: str
    revision_set_id: str
    certified_envelope: Mapping[str, Any]
    gate_results: tuple[GateResult, ...]
    status_counts: Mapping[str, int]
    evidence_root: str
    signer_identity: str | None
    signer_key_id: str | None
    signer_independent: bool
    issued_at: datetime
    status: CertificationStatus
    payload_digest: str
    run_id: str | None
    revision_set_digest: str
    revision_set_revisions: Mapping[str, str]
    proof_graph_digest: str
    evidence_ids: tuple[str, ...]
    production_assessment: bool = False
    signature_receipt_id: str | None = None
    signature_receipt_sha256: str | None = None
    unresolved_risks: tuple[str, ...] = ()

    def to_wire(self) -> dict[str, Any]:
        """Return the exact camel-case JSON DTO validated by the public schema."""

        return {
            "certificateId": self.certificate_id,
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "goalId": self.goal_id,
            "runId": self.run_id,
            "revisionSetId": self.revision_set_id,
            "revisionSetDigest": self.revision_set_digest,
            "revisionSetRevisions": dict(self.revision_set_revisions),
            "proofGraphDigest": self.proof_graph_digest,
            "certifiedEnvelope": dict(self.certified_envelope),
            "gateResults": [
                {
                    "gate": result.gate,
                    "decision": result.decision.value,
                    "evidenceIds": list(result.evidence_ids),
                    "reasons": list(result.reasons),
                }
                for result in self.gate_results
            ],
            "statusCounts": dict(self.status_counts),
            "evidenceIds": list(self.evidence_ids),
            "evidenceRoot": self.evidence_root,
            "signer": {
                "identity": self.signer_identity,
                "keyId": self.signer_key_id,
                "independent": self.signer_independent,
            },
            "issuedAt": self.issued_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "status": self.status.value,
            "payloadDigest": self.payload_digest,
            "productionAssessment": self.production_assessment,
            "signatureReceiptId": self.signature_receipt_id,
            "signatureReceiptSha256": self.signature_receipt_sha256,
            "unresolvedRisks": list(self.unresolved_risks),
        }

    def __post_init__(self) -> None:
        frozen_envelope = freeze_json(self.certified_envelope)
        frozen_counts = freeze_json(self.status_counts)
        frozen_revisions = freeze_json(self.revision_set_revisions)
        if (
            not isinstance(frozen_envelope, Mapping)
            or not isinstance(frozen_counts, Mapping)
            or not isinstance(frozen_revisions, Mapping)
        ):
            raise ValidationError("certificate mappings are invalid")
        object.__setattr__(self, "certified_envelope", frozen_envelope)
        object.__setattr__(self, "status_counts", frozen_counts)
        object.__setattr__(self, "revision_set_revisions", frozen_revisions)
        for name in ("certificate_id", "tenant_id", "project_id", "goal_id", "revision_set_id"):
            _require_text(getattr(self, name), name)
        if any(
            not isinstance(name, str)
            or not name
            or name not in {status.value for status in ProofStatus}
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            for name, count in self.status_counts.items()
        ):
            raise ValidationError("certificate status counts must be non-negative integers")
        require_sha256_digest(self.evidence_root, field="evidence_root")
        require_sha256_digest(self.payload_digest, field="payload_digest")
        require_sha256_digest(self.revision_set_digest, field="revision_set_digest")
        require_sha256_digest(self.proof_graph_digest, field="proof_graph_digest")
        if self.run_id is not None:
            _require_text(self.run_id, "run_id")
        revision_names = {
            "source_repository",
            "baseline_repository",
            "requirements",
            "policy",
            "workflow",
            "model_route",
            "toolchain",
            "environment",
            "domain_pack",
        }
        if set(self.revision_set_revisions) != revision_names:
            raise ValidationError("certificate must bind all nine revision dimensions")
        for name, value in self.revision_set_revisions.items():
            require_sha256_digest(value, field=f"revision_set_revisions.{name}")
        expected_revision_digest = digest_object(
            {
                "revision_set_id": self.revision_set_id,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "goal_id": self.goal_id,
                "revisions": dict(self.revision_set_revisions),
            },
            domain="certification-revision-set",
        )
        if expected_revision_digest != self.revision_set_digest:
            raise ValidationError("certificate revision-set digest is invalid")
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValidationError("certificate evidence ids must be non-empty and unique")
        if any(not isinstance(item, str) or not item for item in self.evidence_ids):
            raise ValidationError("certificate evidence ids are invalid")
        if not isinstance(self.production_assessment, bool):
            raise ValidationError("production_assessment must be boolean")
        if self.signature_receipt_sha256 is not None:
            require_sha256_digest(self.signature_receipt_sha256, field="signature_receipt_sha256")
        if self.signature_receipt_id is not None:
            _require_text(self.signature_receipt_id, "signature_receipt_id")
        if (self.signature_receipt_id is None) != (self.signature_receipt_sha256 is None):
            raise ValidationError("signature receipt id and digest must be present together")
        if self.status in {CertificationStatus.EXTERNALLY_VERIFIED, CertificationStatus.CERTIFIED} and not all(
            (
                self.signer_identity,
                self.signer_key_id,
                self.signer_independent,
                self.signature_receipt_id,
                self.signature_receipt_sha256,
            )
        ):
            raise ValidationError("external certificate lacks a complete signature receipt")
        gate_names = tuple(result.gate for result in self.gate_results)
        if len(set(gate_names)) != len(gate_names):
            raise ValidationError("certificate gate ids must be unique")
        if any(not set(result.evidence_ids).issubset(set(self.evidence_ids)) for result in self.gate_results):
            raise ValidationError("certificate gate evidence is outside the sealed evidence set")
        if self.production_assessment and self.run_id is None:
            raise ValidationError("production assessment requires an exact run id")
        if self.status in {CertificationStatus.EXTERNALLY_VERIFIED, CertificationStatus.CERTIFIED} and self.run_id is None:
            raise ValidationError("external completion status requires an exact run id")
        if self.status is CertificationStatus.CERTIFIED:
            required = {"P05", "E0", "E1", "E2", "E3", "E4", "E5"}
            if not self.production_assessment:
                raise ValidationError("certified status requires a production assessment")
            if set(gate_names) != required or any(
                result.decision is not GateDecision.PASS
                for result in self.gate_results
            ):
                raise ValidationError(
                    "certified status requires exactly one passing result for every production gate"
                )
            if self.unresolved_risks:
                raise ValidationError("certified status cannot retain unresolved risks")
        _require_aware(self.issued_at, "issued_at")


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    tenant_id: str
    project_id: str
    run_id: str
    owner_id: str
    execution_epoch: int
    fencing_generation: int
    token: str
    expires_at: datetime
    sequence: int


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    checkpoint_id: str
    tenant_id: str
    project_id: str
    run_id: str
    execution_epoch: int
    fencing_generation: int
    sequence: int
    payload_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: float
    labels: Mapping[str, str]
    occurred_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_text(self.name, "metric.name")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValidationError("metric.value must be numeric", details={"field": "metric.value"})
        if not math.isfinite(float(self.value)):
            raise ValidationError("metric.value must be finite", details={"field": "metric.value"})
        if not isinstance(self.labels, Mapping):
            raise ValidationError("metric.labels must be an object", details={"field": "metric.labels"})
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
            for key, value in self.labels.items()
        ):
            raise ValidationError("metric labels must be non-empty strings")
        if len(self.labels) > 32:
            raise ValidationError("metric labels exceed the bounded limit")
        _require_aware(self.occurred_at, "metric.occurred_at")
