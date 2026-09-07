"""Fail-closed runtime and artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from .canonical import canonical_digest, finite_json, validate_digest


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


def identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a bounded identifier")
    if ".." in value or "\\" in value:
        raise ValueError(f"{field_name} contains an unsafe path-like value")
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Authority:
    environment_id: str
    profile: str
    scopes: tuple[str, ...] = ()
    fencing_token: int = 0
    approved: bool = False

    def __post_init__(self) -> None:
        identifier(self.environment_id, "environment_id")
        if self.profile not in {"scan-readonly", "transform", "build-sandbox", "test-sandbox", "production-cutover"}:
            raise ValueError("unsupported authority profile")
        if not isinstance(self.scopes, tuple):
            raise ValueError("authority scopes must be a tuple")
        if any(not isinstance(scope, str) or not scope for scope in self.scopes):
            raise ValueError("authority scopes must be non-empty strings")
        if isinstance(self.fencing_token, bool) or not isinstance(self.fencing_token, int) or self.fencing_token < 0:
            raise ValueError("fencing_token must be non-negative")
        if not isinstance(self.approved, bool):
            raise ValueError("approved must be a boolean")
        if self.profile == "production-cutover" and not self.approved:
            raise ValueError("production-cutover requires explicit approval")


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    request_id: str
    tenant_id: str
    project_id: str
    job_id: str
    skill_id: str
    inputs: Mapping[str, Any]
    policy: Mapping[str, Any]
    authority: Authority
    idempotency_key: str
    trace_id: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeRequest":
        if not isinstance(value, Mapping):
            raise ValueError("request must be an object")
        required = {"request_id", "tenant_id", "project_id", "job_id", "skill_id", "inputs", "policy", "authority", "idempotency_key"}
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"request is missing required fields: {missing}")
        authority_value = value["authority"]
        if not isinstance(authority_value, Mapping):
            raise ValueError("authority must be an object")
        scopes_value = authority_value.get("scopes", ())
        if not isinstance(scopes_value, (list, tuple)):
            raise ValueError("authority.scopes must be an array")
        fencing_value = authority_value.get("fencing_token", 0)
        if isinstance(fencing_value, bool) or not isinstance(fencing_value, int):
            raise ValueError("authority.fencing_token must be an integer")
        approved_value = authority_value.get("approved", False)
        if not isinstance(approved_value, bool):
            raise ValueError("authority.approved must be a boolean")
        authority = Authority(
            environment_id=identifier(authority_value.get("environment_id"), "authority.environment_id"),
            profile=authority_value.get("profile"),
            scopes=tuple(scopes_value),
            fencing_token=fencing_value,
            approved=approved_value,
        )
        values = {
            "request_id": identifier(value["request_id"], "request_id"),
            "tenant_id": identifier(value["tenant_id"], "tenant_id"),
            "project_id": identifier(value["project_id"], "project_id"),
            "job_id": identifier(value["job_id"], "job_id"),
            "skill_id": identifier(value["skill_id"], "skill_id"),
            "idempotency_key": identifier(value["idempotency_key"], "idempotency_key"),
        }
        if not isinstance(value["inputs"], Mapping) or not isinstance(value["policy"], Mapping):
            raise ValueError("inputs and policy must be objects")
        inputs = finite_json(dict(value["inputs"]))
        policy = finite_json(dict(value["policy"]))
        trace_id = value.get("trace_id") or canonical_digest({"request_id": values["request_id"], "job_id": values["job_id"]})[7:39]
        values["trace_id"] = identifier(trace_id, "trace_id")
        return cls(inputs=inputs, policy=policy, authority=authority, **values)


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope:
    artifact_type: str
    payload: Mapping[str, Any]
    producer_skill: str
    producer_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    input_hashes: tuple[str, ...] = ()
    policy_snapshot_hash: str = "sha256:" + "0" * 64
    environment_id: str = "local-scan"
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    artifact_id: str = ""
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        identifier(self.artifact_type, "artifact_type")
        identifier(self.producer_skill, "producer_skill")
        identifier(self.producer_version, "producer_version")
        identifier(self.schema_version, "schema_version")
        identifier(self.environment_id, "environment_id")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        validate_digest(self.policy_snapshot_hash)
        for item in self.input_hashes:
            validate_digest(item)
        object.__setattr__(self, "payload", finite_json(dict(self.payload)))
        if not self.artifact_id:
            object.__setattr__(self, "artifact_id", canonical_digest({"type": self.artifact_type, "payload": self.payload, "producer": self.producer_skill}))

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifactId": self.artifact_id,
            "schemaVersion": self.schema_version,
            "type": self.artifact_type,
            "producerSkill": self.producer_skill,
            "producerVersion": self.producer_version,
            "inputHashes": list(self.input_hashes),
            "policySnapshotHash": self.policy_snapshot_hash,
            "environmentId": self.environment_id,
            "evidenceRefs": list(self.evidence_refs),
            "confidence": self.confidence,
            "createdAt": self.created_at,
            "payload": dict(self.payload),
        }
        if include_digest:
            result["digest"] = self.digest
        return result


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    skill_id: str
    handler_id: str
    state: str
    code: str
    artifacts: tuple[ArtifactEnvelope, ...]
    warnings: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    external_evidence: str = "NOT_RUN"
    certification: str = "NOT_CERTIFIED"
    side_effects: bool = False

    def __post_init__(self) -> None:
        identifier(self.skill_id, "skill_id")
        identifier(self.handler_id, "handler_id")
        if self.state not in {"LOCAL_EXECUTED", "PARTIAL_LOCAL_EXECUTED", "PLANNING_ONLY", "BLOCKED"}:
            raise ValueError("invalid capability state")
        if self.external_evidence != "NOT_RUN" or self.certification != "NOT_CERTIFIED":
            raise ValueError("local runtime cannot manufacture external evidence or certification")
        if self.side_effects:
            raise ValueError("local engine side effects must be false")

    def to_dict(self) -> dict[str, Any]:
        return {
            "skillId": self.skill_id,
            "handlerId": self.handler_id,
            "state": self.state,
            "code": self.code,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "warnings": list(self.warnings),
            "unavailable": list(self.unavailable),
            "externalEvidence": self.external_evidence,
            "certification": self.certification,
            "sideEffects": False,
        }
