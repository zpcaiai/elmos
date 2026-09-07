"""Fail-closed typed bridge to the Proof Harness v3 trust boundaries.

The intelligence engine deliberately does not import or instantiate the base
harness.  A host application injects adapters that implement the protocols in
this module and translate the immutable requests into the base v3
``EvidenceService``, external-effect executor, and ``CertificationService``.
Absent adapters return ``NOT_RUN``; they never manufacture evidence or trust.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .canonical import digest_bytes, digest_object, freeze_json, require_sha256_digest
from .errors import IntegrityError, ValidationError


class BridgeStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PREPARED = "PREPARED"
    RECORDED = "RECORDED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"
    CERTIFIED = "CERTIFIED"


def _text(value: object, field: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{field} is required", code="INVALID_BRIDGE_TEXT")
    if len(value) > maximum or any(ord(char) < 0x20 for char in value):
        raise ValidationError(f"{field} is invalid", code="INVALID_BRIDGE_TEXT")
    return value


@dataclass(frozen=True, slots=True)
class BridgeScope:
    """Authenticated scope supplied by the host, never by an operation payload."""

    tenant_id: str
    project_id: str
    actor_id: str
    authority_revision: str
    environment_revision: str
    run_id: str | None = None
    execution_epoch: int = 1
    fencing_generation: int = 1

    def __post_init__(self) -> None:
        for name in ("tenant_id", "project_id", "actor_id"):
            _text(getattr(self, name), name)
        for name in ("authority_revision", "environment_revision"):
            require_sha256_digest(getattr(self, name), field=name)
        if self.run_id is not None:
            _text(self.run_id, "run_id")
        for name in ("execution_epoch", "fencing_generation"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError(f"{name} must be positive", code="INVALID_BRIDGE_FENCE")


@dataclass(frozen=True, slots=True)
class EvidenceWriteRequest:
    scope: BridgeScope
    evidence_id: str
    subject_revision: str
    kind: str
    evidence_class: str
    media_type: str
    content: bytes
    producer_identity: str
    producer_kind: str
    idempotency_key: str
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, BridgeScope):
            raise ValidationError("scope must be BridgeScope")
        for name in (
            "evidence_id",
            "subject_revision",
            "kind",
            "evidence_class",
            "media_type",
            "producer_identity",
            "producer_kind",
            "idempotency_key",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.content, bytes):
            raise ValidationError("evidence content must be immutable bytes", code="CONTENT_NOT_BYTES")
        if not self.content:
            raise ValidationError("evidence content cannot be empty", code="EMPTY_EVIDENCE")
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValidationError("evidence expiry must be timezone-aware")

    @property
    def content_digest(self) -> str:
        return digest_bytes(self.content, domain="base-v3-evidence-content")


@dataclass(frozen=True, slots=True)
class ExternalEffectRequest:
    scope: BridgeScope
    effect_id: str
    provider: str
    operation: str
    idempotency_key: str
    request: Mapping[str, Any]
    request_digest: str
    lease_token: str
    lease_generation: int
    reconciliation_strategy: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, BridgeScope):
            raise ValidationError("scope must be BridgeScope")
        for name in (
            "effect_id",
            "provider",
            "operation",
            "idempotency_key",
            "lease_token",
            "reconciliation_strategy",
        ):
            _text(getattr(self, name), name, maximum=4096 if name == "lease_token" else 1024)
        if isinstance(self.lease_generation, bool) or not isinstance(self.lease_generation, int) or self.lease_generation < 1:
            raise ValidationError("lease_generation must be positive")
        require_sha256_digest(self.request_digest, field="request_digest")
        frozen = freeze_json(self.request)
        if not isinstance(frozen, Mapping):
            raise ValidationError("external effect request must be an object")
        object.__setattr__(self, "request", frozen)
        actual = digest_object(frozen, domain="pdhi-external-effect-request")
        if actual != self.request_digest:
            raise IntegrityError(
                "external effect request digest mismatch",
                code="EFFECT_REQUEST_DIGEST_MISMATCH",
                details={"claimed": self.request_digest, "actual": actual},
            )


@dataclass(frozen=True, slots=True)
class CertificationSubmission:
    scope: BridgeScope
    certificate_id: str
    bundle_digest: str
    bundle_bytes: bytes
    target_level: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, BridgeScope):
            raise ValidationError("scope must be BridgeScope")
        for name in ("certificate_id", "target_level", "idempotency_key"):
            _text(getattr(self, name), name)
        require_sha256_digest(self.bundle_digest, field="bundle_digest")
        if not isinstance(self.bundle_bytes, bytes) or not self.bundle_bytes:
            raise ValidationError("certification bundle bytes are required")
        actual = digest_bytes(self.bundle_bytes, domain="pdhi-certification-bundle")
        if actual != self.bundle_digest:
            raise IntegrityError(
                "certification bundle digest mismatch",
                code="CERTIFICATION_BUNDLE_DIGEST_MISMATCH",
                details={"claimed": self.bundle_digest, "actual": actual},
            )


@dataclass(frozen=True, slots=True)
class BridgeResult:
    status: BridgeStatus
    reference_id: str | None
    receipt_digest: str | None
    detail: Mapping[str, Any]
    external_evidence_status: str
    certification_status: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, BridgeStatus):
            raise ValidationError("bridge status is invalid")
        if self.reference_id is not None:
            _text(self.reference_id, "reference_id")
        if self.receipt_digest is not None:
            require_sha256_digest(self.receipt_digest, field="receipt_digest")
        frozen = freeze_json(self.detail)
        if not isinstance(frozen, Mapping):
            raise ValidationError("bridge detail must be an object")
        object.__setattr__(self, "detail", frozen)
        if self.status in {
            BridgeStatus.RECORDED,
            BridgeStatus.EXTERNALLY_VERIFIED,
            BridgeStatus.CERTIFIED,
        } and (self.reference_id is None or self.receipt_digest is None):
            raise ValidationError("successful bridge result requires a durable receipt")
        if self.status is BridgeStatus.CERTIFIED and self.certification_status != "CERTIFIED":
            raise ValidationError("CERTIFIED bridge status requires certified result")
        if self.certification_status == "CERTIFIED" and self.status is not BridgeStatus.CERTIFIED:
            raise ValidationError("certification cannot be asserted by a non-certified bridge result")

    @classmethod
    def not_run(cls, boundary: str) -> "BridgeResult":
        return cls(
            status=BridgeStatus.NOT_RUN,
            reference_id=None,
            receipt_digest=None,
            detail=MappingProxyType(
                {
                    "boundary": _text(boundary, "boundary"),
                    "reason": "trusted base v3 adapter is not configured",
                }
            ),
            external_evidence_status="NOT_RUN",
            certification_status="NOT_CERTIFIED",
        )


@runtime_checkable
class EvidencePort(Protocol):
    """Adapter to base v3 byte-bound ``EvidenceService``."""

    trusted: bool

    def record(self, request: EvidenceWriteRequest) -> BridgeResult: ...

    def readiness(self) -> Mapping[str, Any]: ...


@runtime_checkable
class ExternalEffectPort(Protocol):
    """Adapter to the base v3 durable effect/executor boundary."""

    trusted: bool

    def execute(self, request: ExternalEffectRequest) -> BridgeResult: ...

    def readiness(self) -> Mapping[str, Any]: ...


@runtime_checkable
class CertificationPort(Protocol):
    """Adapter to base v3 conservative certification service."""

    trusted: bool
    independent: bool

    def submit(self, request: CertificationSubmission) -> BridgeResult: ...

    def readiness(self) -> Mapping[str, Any]: ...


class _NotConfiguredEvidencePort:
    trusted = False

    def record(self, request: EvidenceWriteRequest) -> BridgeResult:
        return BridgeResult.not_run("base-v3-evidence")

    def readiness(self) -> Mapping[str, Any]:
        return MappingProxyType({"status": "NOT_CONFIGURED", "external_evidence": "NOT_RUN"})


class _NotConfiguredEffectPort:
    trusted = False

    def execute(self, request: ExternalEffectRequest) -> BridgeResult:
        return BridgeResult.not_run("base-v3-external-effect")

    def readiness(self) -> Mapping[str, Any]:
        return MappingProxyType({"status": "NOT_CONFIGURED", "external_effects": "NOT_RUN"})


class _NotConfiguredCertificationPort:
    trusted = False
    independent = False

    def submit(self, request: CertificationSubmission) -> BridgeResult:
        return BridgeResult.not_run("base-v3-certification")

    def readiness(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {"status": "NOT_CONFIGURED", "independent_verification": "NOT_RUN", "certification": "NOT_CERTIFIED"}
        )


class ProofHarnessV3Bridge:
    """Host-injected composition of the three base-v3 trust ports."""

    def __init__(
        self,
        *,
        evidence: EvidencePort | None = None,
        effects: ExternalEffectPort | None = None,
        certification: CertificationPort | None = None,
    ) -> None:
        self._evidence = evidence or _NotConfiguredEvidencePort()
        self._effects = effects or _NotConfiguredEffectPort()
        self._certification = certification or _NotConfiguredCertificationPort()
        for name, port in (
            ("evidence", self._evidence),
            ("effects", self._effects),
            ("certification", self._certification),
        ):
            if not hasattr(port, "readiness"):
                raise ValidationError(f"{name} port does not implement readiness")

    def record_evidence(self, request: EvidenceWriteRequest) -> BridgeResult:
        if not self._evidence.trusted:
            return BridgeResult.not_run("base-v3-evidence")
        return self._evidence.record(request)

    def execute_effect(self, request: ExternalEffectRequest) -> BridgeResult:
        if not self._effects.trusted:
            return BridgeResult.not_run("base-v3-external-effect")
        return self._effects.execute(request)

    def submit_certification(self, request: CertificationSubmission) -> BridgeResult:
        if not self._certification.trusted or not self._certification.independent:
            return BridgeResult.not_run("base-v3-certification")
        return self._certification.submit(request)

    def readiness(self) -> Mapping[str, Any]:
        ports = {
            "evidence": dict(self._evidence.readiness()),
            "effects": dict(self._effects.readiness()),
            "certification": dict(self._certification.readiness()),
        }
        return MappingProxyType(
            {
                "ports": ports,
                "external_evidence": "NOT_RUN"
                if not self._evidence.trusted
                else ports["evidence"].get("external_evidence", "UNKNOWN"),
                "external_effects": "NOT_RUN"
                if not self._effects.trusted
                else ports["effects"].get("external_effects", "UNKNOWN"),
                "certification": "NOT_CERTIFIED"
                if not (self._certification.trusted and self._certification.independent)
                else ports["certification"].get("certification", "UNKNOWN"),
            }
        )


__all__ = [
    "BridgeResult",
    "BridgeScope",
    "BridgeStatus",
    "CertificationPort",
    "CertificationSubmission",
    "EvidencePort",
    "EvidenceWriteRequest",
    "ExternalEffectPort",
    "ExternalEffectRequest",
    "ProofHarnessV3Bridge",
]
