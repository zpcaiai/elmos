"""Typed public contracts for the semantic-assurance runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .canonical import (
    canonical_value,
    reject_inline_secrets,
    require_bounded_json,
    validate_digest,
    validate_identifier,
)


class ExecutionStatus(str, Enum):
    LOCAL_EXECUTED = "LOCAL_EXECUTED"
    REQUIRES_ADAPTER = "REQUIRES_ADAPTER"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"


class EvidenceStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    LOCAL_EXECUTED_SELF_ATTESTED = "LOCAL_EXECUTED_SELF_ATTESTED"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXTERNAL_EVIDENCE_PENDING = "EXTERNAL_EVIDENCE_PENDING"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


class CapabilityState(str, Enum):
    CODE_COMPLETE_LOCAL_BOUNDED = "CODE_COMPLETE_LOCAL_BOUNDED"
    CODE_COMPLETE_ADAPTER_REQUIRED = "CODE_COMPLETE_ADAPTER_REQUIRED"
    CODE_COMPLETE_EXTERNAL_GATE_REQUIRED = "CODE_COMPLETE_EXTERNAL_GATE_REQUIRED"


class Operation(str, Enum):
    MODEL_NORMALIZATION = "MODEL_NORMALIZATION"
    SEMANTIC_COMPARISON = "SEMANTIC_COMPARISON"
    GRAPH_ANALYSIS = "GRAPH_ANALYSIS"
    COVERAGE_ANALYSIS = "COVERAGE_ANALYSIS"
    CORPUS_GOVERNANCE = "CORPUS_GOVERNANCE"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"
    NATIVE_EXECUTION = "NATIVE_EXECUTION"
    FORMAL_EXECUTION = "FORMAL_EXECUTION"
    FUZZ_EXECUTION = "FUZZ_EXECUTION"
    GATE_EVALUATION = "GATE_EVALUATION"
    CACHE_INVALIDATION = "CACHE_INVALIDATION"
    COUNTEREXAMPLE_REPLAY = "COUNTEREXAMPLE_REPLAY"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class TrustedIdentity:
    tenant_id: str
    project_id: str
    actor_id: str
    roles: tuple[str, ...] = ()
    authorization_ref: str | None = None

    def __post_init__(self) -> None:
        validate_identifier(self.tenant_id, "identity.tenantId")
        validate_identifier(self.project_id, "identity.projectId")
        validate_identifier(self.actor_id, "identity.actorId")
        if self.authorization_ref is not None:
            validate_identifier(self.authorization_ref, "identity.authorizationRef")
        for index, role in enumerate(self.roles):
            validate_identifier(role, f"identity.roles[{index}]")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("identity.roles must not contain duplicates")


@dataclass(frozen=True, slots=True)
class AssuranceScope:
    tenant_id: str
    project_id: str
    run_id: str
    snapshot_id: str
    snapshot_digest: str
    source_digest: str
    target_digest: str
    environment_digest: str
    semantic_profile_digest: str
    toolchain_digest: str
    corpus_digest: str
    assumptions_digest: str
    route_id: str
    source_technology: str
    source_dialect: str
    source_runtime: str
    target_technology: str
    target_dialect: str
    target_runtime: str

    def __post_init__(self) -> None:
        for name, value in (
            ("tenantId", self.tenant_id),
            ("projectId", self.project_id),
            ("runId", self.run_id),
            ("snapshotId", self.snapshot_id),
            ("routeId", self.route_id),
            ("sourceTechnology", self.source_technology),
            ("sourceDialect", self.source_dialect),
            ("sourceRuntime", self.source_runtime),
            ("targetTechnology", self.target_technology),
            ("targetDialect", self.target_dialect),
            ("targetRuntime", self.target_runtime),
        ):
            validate_identifier(value, f"scope.{name}")
        for name, value in (
            ("snapshotDigest", self.snapshot_digest),
            ("sourceDigest", self.source_digest),
            ("targetDigest", self.target_digest),
            ("environmentDigest", self.environment_digest),
            ("semanticProfileDigest", self.semantic_profile_digest),
            ("toolchainDigest", self.toolchain_digest),
            ("corpusDigest", self.corpus_digest),
            ("assumptionsDigest", self.assumptions_digest),
        ):
            validate_digest(value, f"scope.{name}")

    def to_dict(self) -> dict[str, str]:
        return {
            "tenantId": self.tenant_id,
            "projectId": self.project_id,
            "runId": self.run_id,
            "snapshotId": self.snapshot_id,
            "snapshotDigest": validate_digest(self.snapshot_digest),
            "sourceDigest": validate_digest(self.source_digest),
            "targetDigest": validate_digest(self.target_digest),
            "environmentDigest": validate_digest(self.environment_digest),
            "semanticProfileDigest": validate_digest(self.semantic_profile_digest),
            "toolchainDigest": validate_digest(self.toolchain_digest),
            "corpusDigest": validate_digest(self.corpus_digest),
            "assumptionsDigest": validate_digest(self.assumptions_digest),
            "routeId": self.route_id,
            "sourceTechnology": self.source_technology,
            "sourceDialect": self.source_dialect,
            "sourceRuntime": self.source_runtime,
            "targetTechnology": self.target_technology,
            "targetDialect": self.target_dialect,
            "targetRuntime": self.target_runtime,
        }

    @property
    def contains_unknown_tuple(self) -> bool:
        return any(
            value.lower() in {"unknown", "unspecified", "not-run"}
            for value in (
                self.source_technology,
                self.source_dialect,
                self.source_runtime,
                self.target_technology,
                self.target_dialect,
                self.target_runtime,
            )
        )


_SCOPE_FIELDS = {
    "tenantId": "tenant_id",
    "projectId": "project_id",
    "runId": "run_id",
    "snapshotId": "snapshot_id",
    "snapshotDigest": "snapshot_digest",
    "sourceDigest": "source_digest",
    "targetDigest": "target_digest",
    "environmentDigest": "environment_digest",
    "semanticProfileDigest": "semantic_profile_digest",
    "toolchainDigest": "toolchain_digest",
    "corpusDigest": "corpus_digest",
    "assumptionsDigest": "assumptions_digest",
    "routeId": "route_id",
    "sourceTechnology": "source_technology",
    "sourceDialect": "source_dialect",
    "sourceRuntime": "source_runtime",
    "targetTechnology": "target_technology",
    "targetDialect": "target_dialect",
    "targetRuntime": "target_runtime",
}


@dataclass(frozen=True, slots=True)
class SkillRequest:
    schema_version: str
    subject_id: str
    idempotency_key: str
    scope: AssuranceScope
    payload: dict[str, Any]
    allowed_effects: tuple[str, ...] = ()

    @classmethod
    def parse(
        cls,
        value: Any,
        identity: TrustedIdentity,
        *,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> SkillRequest:
        document = require_bounded_json(value, path="request", max_bytes=max_bytes)
        if not isinstance(document, dict):
            raise ValueError("request must be an object")
        allowed = {
            "schemaVersion",
            "subjectId",
            "idempotencyKey",
            "scope",
            "payload",
            "allowedEffects",
        }
        extra = sorted(set(document) - allowed)
        if extra:
            raise ValueError(f"request contains unsupported fields: {extra}")
        if document.get("schemaVersion") != "1.0":
            raise ValueError("request.schemaVersion must be 1.0")
        scope_value = document.get("scope")
        if not isinstance(scope_value, dict):
            raise ValueError("request.scope must be an object")
        missing = [name for name in _SCOPE_FIELDS if name not in scope_value]
        extra_scope = sorted(set(scope_value) - set(_SCOPE_FIELDS))
        if missing or extra_scope:
            raise ValueError(
                f"request.scope fields invalid; missing={missing}, extra={extra_scope}"
            )
        kwargs = {
            attribute: scope_value[source]
            for source, attribute in _SCOPE_FIELDS.items()
        }
        scope = AssuranceScope(**kwargs)
        if (
            scope.tenant_id != identity.tenant_id
            or scope.project_id != identity.project_id
        ):
            raise PermissionError("request scope does not match trusted identity")
        payload = document.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("request.payload must be an object")
        reject_inline_secrets(payload, "request.payload.")
        effects = document.get("allowedEffects", [])
        if not isinstance(effects, list) or any(
            not isinstance(item, str) for item in effects
        ):
            raise ValueError("request.allowedEffects must be an array of strings")
        unsupported_effects = sorted(set(effects) - {"artifact-write"})
        if unsupported_effects:
            raise PermissionError(
                f"local semantic runtime cannot authorize effects: {unsupported_effects}"
            )
        if len(set(effects)) != len(effects):
            raise ValueError("request.allowedEffects must not contain duplicates")
        return cls(
            schema_version="1.0",
            subject_id=validate_identifier(document.get("subjectId"), "subjectId"),
            idempotency_key=validate_identifier(
                document.get("idempotencyKey"), "idempotencyKey"
            ),
            scope=scope,
            payload=canonical_value(payload),
            allowed_effects=tuple(effects),
        )

    def to_digest_document(self, skill_name: str) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "skillName": skill_name,
            "subjectId": self.subject_id,
            "scope": self.scope.to_dict(),
            "payload": self.payload,
            "allowedEffects": list(self.allowed_effects),
        }


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    logical_path: str
    media_type: str
    content_digest: str
    byte_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "logicalPath": self.logical_path,
            "mediaType": self.media_type,
            "contentDigest": validate_digest(self.content_digest),
            "byteCount": self.byte_count,
        }


@dataclass(frozen=True, slots=True)
class SkillOutcome:
    skill_name: str
    source_skill_id: str
    installed_name: str
    handler_id: str
    operation: Operation
    capability_state: CapabilityState
    execution_status: ExecutionStatus
    evidence_status: EvidenceStatus
    result: dict[str, Any]
    diagnostics: tuple[dict[str, Any], ...] = ()
    artifacts: tuple[ArtifactRecord, ...] = ()
    implementation_state: str = "RUNTIME_CODE_COMPLETE"
    external_evidence_status: str = "NOT_RUN"
    certification_status: str = "NOT_CERTIFIED"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        if self.certification_status != "NOT_CERTIFIED":
            raise ValueError("local runtime cannot promote certification status")
        if self.external_evidence_status != "NOT_RUN":
            raise ValueError("local runtime cannot manufacture external evidence")
        return {
            "skillName": self.skill_name,
            "sourceSkillId": self.source_skill_id,
            "installedName": self.installed_name,
            "handlerId": self.handler_id,
            "operation": self.operation.value,
            "capabilityState": self.capability_state.value,
            "implementationState": self.implementation_state,
            "executionStatus": self.execution_status.value,
            "evidenceStatus": self.evidence_status.value,
            "result": canonical_value(self.result),
            "diagnostics": [canonical_value(item) for item in self.diagnostics],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "externalEvidenceStatus": self.external_evidence_status,
            "certificationStatus": self.certification_status,
            "createdAt": self.created_at,
        }


__all__ = [
    "ArtifactRecord",
    "AssuranceScope",
    "CapabilityState",
    "EvidenceStatus",
    "ExecutionStatus",
    "Operation",
    "SkillOutcome",
    "SkillRequest",
    "TrustedIdentity",
    "utc_now",
]
