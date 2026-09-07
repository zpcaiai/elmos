"""Independent external-evidence receipts for the Formal Release Gate."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from .canonical import canonical_json, digest_value, validate_digest, validate_identifier
from .contracts import Scope


class GateEvidenceError(ValueError):
    """Raised when a release-gate evidence receipt fails closed."""


_GATES = {
    "P05_DEPLOYMENT_COMPLETE",
    "E1_STATIC",
    "E2_MODEL",
    "E3_DIFFERENTIAL",
    "E4_FAILURE_INJECTION",
    "E5_CUSTOMER_GOLDEN_ROUTE",
}


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateEvidenceError(f"{label} must be an explicit UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise GateEvidenceError(f"{label} is invalid") from exc
    if parsed.tzinfo != timezone.utc:
        raise GateEvidenceError(f"{label} must use UTC")
    return parsed


@dataclass(frozen=True, slots=True)
class ExternalGateEvidenceReceipt:
    receipt_id: str
    scope_digest: str
    subject_id: str
    gate: str
    decision_input_digest: str
    evidence_digest: str
    deployment_complete: bool
    external_evidence_complete: bool
    executor_id: str
    independent_verifier_id: str
    issued_at: str
    expires_at: str
    key_id: str
    signature_algorithm: str
    signature: str
    format: str = "elmos-formal-external-gate-evidence/v1"

    def __post_init__(self) -> None:
        if self.format != "elmos-formal-external-gate-evidence/v1":
            raise GateEvidenceError("external gate evidence format is unsupported")
        for name, value in (
            ("receiptId", self.receipt_id),
            ("subjectId", self.subject_id),
            ("executorId", self.executor_id),
            ("independentVerifierId", self.independent_verifier_id),
            ("keyId", self.key_id),
        ):
            validate_identifier(value, f"gateEvidence.{name}")
        if self.executor_id == self.independent_verifier_id:
            raise GateEvidenceError(
                "executor and independent verifier must be different identities"
            )
        if self.gate not in _GATES:
            raise GateEvidenceError("external gate evidence names an unknown gate")
        for name, value in (
            ("scopeDigest", self.scope_digest),
            ("decisionInputDigest", self.decision_input_digest),
            ("evidenceDigest", self.evidence_digest),
        ):
            validate_digest(value, f"gateEvidence.{name}")
        if not isinstance(self.deployment_complete, bool):
            raise GateEvidenceError("deploymentComplete must be boolean")
        if not isinstance(self.external_evidence_complete, bool):
            raise GateEvidenceError("externalEvidenceComplete must be boolean")
        issued = _timestamp(self.issued_at, "gateEvidence.issuedAt")
        expires = _timestamp(self.expires_at, "gateEvidence.expiresAt")
        if expires <= issued:
            raise GateEvidenceError("external gate evidence expiry must follow issue time")
        if expires - issued > timedelta(days=30):
            raise GateEvidenceError("external gate evidence lifetime exceeds 30 days")
        if self.signature_algorithm != "ED25519":
            raise GateEvidenceError("external gate evidence must use Ed25519")
        try:
            decoded = base64.b64decode(self.signature, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise GateEvidenceError("external gate evidence signature is invalid") from exc
        if len(decoded) != 64:
            raise GateEvidenceError("Ed25519 signature must contain 64 bytes")

    @classmethod
    def from_dict(cls, value: Any) -> ExternalGateEvidenceReceipt:
        expected = {
            "format",
            "receiptId",
            "scopeDigest",
            "subjectId",
            "gate",
            "decisionInputDigest",
            "evidenceDigest",
            "deploymentComplete",
            "externalEvidenceComplete",
            "executorId",
            "independentVerifierId",
            "issuedAt",
            "expiresAt",
            "keyId",
            "signatureAlgorithm",
            "signature",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise GateEvidenceError(
                "external gate evidence must contain the exact v1 fields"
            )
        return cls(
            format=value["format"],
            receipt_id=value["receiptId"],
            scope_digest=value["scopeDigest"],
            subject_id=value["subjectId"],
            gate=value["gate"],
            decision_input_digest=value["decisionInputDigest"],
            evidence_digest=value["evidenceDigest"],
            deployment_complete=value["deploymentComplete"],
            external_evidence_complete=value["externalEvidenceComplete"],
            executor_id=value["executorId"],
            independent_verifier_id=value["independentVerifierId"],
            issued_at=value["issuedAt"],
            expires_at=value["expiresAt"],
            key_id=value["keyId"],
            signature_algorithm=value["signatureAlgorithm"],
            signature=value["signature"],
        )

    def signed_document(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "receiptId": self.receipt_id,
            "scopeDigest": self.scope_digest,
            "subjectId": self.subject_id,
            "gate": self.gate,
            "decisionInputDigest": self.decision_input_digest,
            "evidenceDigest": self.evidence_digest,
            "deploymentComplete": self.deployment_complete,
            "externalEvidenceComplete": self.external_evidence_complete,
            "executorId": self.executor_id,
            "independentVerifierId": self.independent_verifier_id,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "keyId": self.key_id,
            "signatureAlgorithm": self.signature_algorithm,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.signed_document(), "signature": self.signature}


@dataclass(frozen=True, slots=True)
class VerifiedGateEvidence:
    receipt_id: str
    receipt_digest: str
    evidence_digest: str
    verifier_key_id: str
    deployment_complete: bool
    external_evidence_complete: bool
    verification_status: str = "INDEPENDENT_EXTERNAL_VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "receiptId": self.receipt_id,
            "receiptDigest": self.receipt_digest,
            "evidenceDigest": self.evidence_digest,
            "verifierKeyId": self.verifier_key_id,
            "deploymentComplete": self.deployment_complete,
            "externalEvidenceComplete": self.external_evidence_complete,
            "verificationStatus": self.verification_status,
        }


class GateEvidenceVerifier(Protocol):
    def verify(
        self,
        value: Any,
        *,
        scope: Scope,
        subject_id: str,
        gate: str,
        decision_input_digest: str,
        now: datetime | None = None,
    ) -> VerifiedGateEvidence:
        """Verify exact scope, decision input, freshness and external signature."""


class Ed25519GateEvidenceVerifier:
    """Verify receipts against an operator-owned independent trust store."""

    def __init__(
        self,
        public_keys: Mapping[str, bytes],
        *,
        revoked_key_ids: frozenset[str] = frozenset(),
    ) -> None:
        if not isinstance(public_keys, Mapping) or not public_keys:
            raise GateEvidenceError("at least one external verifier public key is required")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ImportError as exc:  # pragma: no cover - packaging dependency guard
            raise GateEvidenceError(
                "cryptography is required for Ed25519 gate evidence verification"
            ) from exc
        resolved: dict[str, Any] = {}
        for key_id, raw in public_keys.items():
            validate_identifier(key_id, "gateEvidence.keyId")
            if not isinstance(raw, bytes) or len(raw) != 32:
                raise GateEvidenceError(
                    f"Ed25519 public key must contain 32 bytes: {key_id}"
                )
            resolved[key_id] = Ed25519PublicKey.from_public_bytes(raw)
        unknown_revocations = set(revoked_key_ids) - set(resolved)
        if unknown_revocations:
            raise GateEvidenceError(
                "revoked gate-evidence keys are absent from the trust store"
            )
        self._keys = resolved
        self._revoked = frozenset(revoked_key_ids)

    def verify(
        self,
        value: Any,
        *,
        scope: Scope,
        subject_id: str,
        gate: str,
        decision_input_digest: str,
        now: datetime | None = None,
    ) -> VerifiedGateEvidence:
        try:
            receipt = ExternalGateEvidenceReceipt.from_dict(value)
        except GateEvidenceError:
            raise
        except (TypeError, ValueError) as exc:
            raise GateEvidenceError(
                "external gate evidence contains an invalid field"
            ) from exc
        expected = (
            digest_value(scope.to_dict()),
            validate_identifier(subject_id, "subjectId"),
            gate,
            validate_digest(decision_input_digest, "decisionInputDigest"),
        )
        actual = (
            receipt.scope_digest,
            receipt.subject_id,
            receipt.gate,
            receipt.decision_input_digest,
        )
        if actual != expected:
            raise GateEvidenceError(
                "external gate evidence is not bound to the exact decision scope"
            )
        current = now or datetime.now(timezone.utc)
        issued = _timestamp(receipt.issued_at, "gateEvidence.issuedAt")
        expires = _timestamp(receipt.expires_at, "gateEvidence.expiresAt")
        if issued > current + timedelta(seconds=30):
            raise GateEvidenceError("external gate evidence issue time is in the future")
        if expires <= current:
            raise GateEvidenceError("external gate evidence has expired")
        if receipt.key_id in self._revoked:
            raise GateEvidenceError("external gate evidence key is revoked")
        public_key = self._keys.get(receipt.key_id)
        if public_key is None:
            raise GateEvidenceError("external gate evidence key is untrusted")
        signature = base64.b64decode(receipt.signature, validate=True)
        try:
            public_key.verify(signature, canonical_json(receipt.signed_document()))
        except Exception as exc:
            raise GateEvidenceError(
                "external gate evidence signature verification failed"
            ) from exc
        return VerifiedGateEvidence(
            receipt_id=receipt.receipt_id,
            receipt_digest=digest_value(receipt.to_dict()),
            evidence_digest=receipt.evidence_digest,
            verifier_key_id=receipt.key_id,
            deployment_complete=receipt.deployment_complete,
            external_evidence_complete=receipt.external_evidence_complete,
        )


__all__ = [
    "Ed25519GateEvidenceVerifier",
    "ExternalGateEvidenceReceipt",
    "GateEvidenceError",
    "GateEvidenceVerifier",
    "VerifiedGateEvidence",
]
