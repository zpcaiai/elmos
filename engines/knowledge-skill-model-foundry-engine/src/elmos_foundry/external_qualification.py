"""End-to-end verification of real Foundry external qualification material.

The verifier consumes externally issued receipts and public trust material.  It
does not execute providers, hold private keys, create signatures, or manufacture
missing evidence.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from .canonical import canonical_digest, require_identifier, validate_digest
from .domain import CertificationStatus
from .external_assurance import (
    CertificationRequest,
    ExternalAssuranceError,
    ExternalRunRequest,
    IndependentAcceptanceRequest,
    SignatureVerifier,
    evaluate_certification,
    verify_external_run_receipt,
    verify_independent_acceptance,
    verify_signed_external_receipt,
)


class SignatureBackend(Protocol):
    """Existing asymmetric verification backend contract."""

    def verify(self, public_key: bytes, signature: bytes, payload: bytes) -> None: ...


TRUST_ROLES = frozenset(
    {
        "PROVIDER",
        "TRAINING_PROVIDER",
        "DEPLOYMENT_PROVIDER",
        "INDEPENDENT_VERIFIER",
        "CERTIFICATION_AUTHORITY",
    }
)


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(f"{label} fields differ: missing={missing}, extra={extra}")


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _strings(value: Sequence[Any], label: str) -> tuple[str, ...]:
    return tuple(_string(item, f"{label}[]") for item in value)


@dataclass(frozen=True, slots=True)
class ProviderEvidenceRequest:
    provider_id: str
    provider_version: str
    executable_digest: str
    request_binding_digest: str
    route_id: str
    route_digest: str
    operation: str
    outputs_digest: str

    def __post_init__(self) -> None:
        for name in ("provider_id", "provider_version", "route_id", "operation"):
            require_identifier(getattr(self, name), name)
        validate_digest(self.executable_digest, "executable_digest")
        validate_digest(self.request_binding_digest, "request_binding_digest")
        validate_digest(self.outputs_digest, "outputs_digest")
        if len(self.route_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.route_digest
        ):
            raise ValueError("route_digest must be 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class ExternalTrustKey:
    authority_id: str
    key_id: str
    public_key: bytes
    roles: tuple[str, ...]
    not_before: int
    not_after: int
    revoked: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.authority_id, "authority_id")
        require_identifier(self.key_id, "key_id")
        if len(self.public_key) != 32:
            raise ValueError("Ed25519 public key must contain 32 bytes")
        roles = tuple(self.roles)
        if not roles or roles != tuple(sorted(set(roles))) or not set(roles) <= TRUST_ROLES:
            raise ValueError("trust key roles must be non-empty, unique, sorted, and supported")
        for value, label in ((self.not_before, "not_before"), (self.not_after, "not_after")):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive epoch second")
        if self.not_after <= self.not_before:
            raise ValueError("trust key validity interval is invalid")


class ExternalTrustStore:
    """Verify-only Ed25519 trust set with exact authority roles and revocation."""

    def __init__(
        self,
        *,
        trust_epoch: int,
        keys: Sequence[ExternalTrustKey],
        backend: SignatureBackend,
    ) -> None:
        if isinstance(trust_epoch, bool) or not isinstance(trust_epoch, int) or trust_epoch <= 0:
            raise ValueError("trust_epoch must be a positive integer")
        values = tuple(keys)
        identities = {(key.authority_id, key.key_id) for key in values}
        if not values or len(identities) != len(values):
            raise ValueError("trust keys must be non-empty and uniquely identified")
        if len({key.public_key for key in values}) != len(values):
            raise ValueError("one public key cannot represent multiple trust identities")
        authority_roles: dict[str, set[str]] = {}
        for key in values:
            authority_roles.setdefault(key.authority_id, set()).update(key.roles)
        separated_roles = {"INDEPENDENT_VERIFIER", "CERTIFICATION_AUTHORITY"}
        for authority_id, roles in authority_roles.items():
            if roles & separated_roles and len(roles) != 1:
                raise ValueError(
                    f"independent and certification roles must be isolated: {authority_id}"
                )
        self.trust_epoch = trust_epoch
        self._keys = MappingProxyType({(key.authority_id, key.key_id): key for key in values})
        self._backend = backend
        self.digest = canonical_digest(
            {
                "schema_version": "elmos.foundry.external-trust-store.v1",
                "trust_epoch": trust_epoch,
                "keys": [
                    {
                        "authority_id": key.authority_id,
                        "key_id": key.key_id,
                        "public_key_base64": base64.b64encode(key.public_key).decode("ascii"),
                        "roles": list(key.roles),
                        "not_before": key.not_before,
                        "not_after": key.not_after,
                        "revoked": key.revoked,
                    }
                    for key in sorted(values, key=lambda item: (item.authority_id, item.key_id))
                ],
            }
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        backend: SignatureBackend,
    ) -> "ExternalTrustStore":
        _exact_fields(value, {"schema_version", "trust_epoch", "keys"}, "trust store")
        if value.get("schema_version") != "elmos.foundry.external-trust-store.v1":
            raise ValueError("unsupported external trust-store schema")
        raw_keys = value.get("keys")
        if not isinstance(raw_keys, Sequence) or isinstance(raw_keys, (str, bytes, bytearray)):
            raise ValueError("trust store keys must be an array")
        keys: list[ExternalTrustKey] = []
        fields = {
            "authority_id",
            "key_id",
            "public_key_base64",
            "roles",
            "not_before",
            "not_after",
            "revoked",
        }
        for index, raw in enumerate(raw_keys):
            if not isinstance(raw, Mapping):
                raise ValueError(f"trust key {index} must be an object")
            _exact_fields(raw, fields, f"trust key {index}")
            encoded = raw.get("public_key_base64")
            if not isinstance(encoded, str):
                raise ValueError(f"trust key {index} public key must be base64 text")
            try:
                public_key = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(f"trust key {index} public key is invalid base64") from exc
            roles = raw.get("roles")
            if not isinstance(roles, Sequence) or isinstance(roles, (str, bytes, bytearray)):
                raise ValueError(f"trust key {index} roles must be an array")
            keys.append(
                ExternalTrustKey(
                    authority_id=_string(raw.get("authority_id"), "authority_id"),
                    key_id=_string(raw.get("key_id"), "key_id"),
                    public_key=public_key,
                    roles=_strings(roles, "roles"),
                    not_before=_integer(raw.get("not_before"), "not_before"),
                    not_after=_integer(raw.get("not_after"), "not_after"),
                    revoked=_boolean(raw.get("revoked"), "revoked"),
                )
            )
        return cls(
            trust_epoch=_integer(value.get("trust_epoch"), "trust_epoch"),
            keys=keys,
            backend=backend,
        )

    def verifier(self, required_role: str, *, now: int) -> SignatureVerifier:
        if required_role not in TRUST_ROLES:
            raise ValueError("required trust role is unsupported")
        if isinstance(now, bool) or not isinstance(now, int) or now <= 0:
            raise ValueError("verification time must be a positive epoch second")

        def verify(authority_id: str, key_id: str, digest: str, signature: str) -> bool:
            key = self._keys.get((authority_id, key_id))
            if (
                key is None
                or key.revoked
                or required_role not in key.roles
                or not (key.not_before <= now < key.not_after)
            ):
                return False
            try:
                raw_signature = base64.b64decode(signature, validate=True)
                if len(raw_signature) != 64:
                    return False
                self._backend.verify(key.public_key, raw_signature, digest.encode("ascii"))
            except Exception:
                # Backends such as cryptography raise their own InvalidSignature
                # type. No backend exception may escape as an accepted or
                # indeterminate trust decision.
                return False
            return True

        return verify


def verify_provider_evidence_receipt(
    request: ProviderEvidenceRequest,
    receipt: Mapping[str, Any],
    *,
    verifier: SignatureVerifier,
) -> str:
    expected = {
        "schema_version": "elmos.foundry.provider-receipt.v1",
        "provider_id": request.provider_id,
        "provider_version": request.provider_version,
        "executable_digest": request.executable_digest,
        "request_binding_digest": request.request_binding_digest,
        "route_id": request.route_id,
        "route_digest": request.route_digest,
        "operation": request.operation,
        "outcome": "CONFIRMED",
        "outputs_digest": request.outputs_digest,
    }
    if any(receipt.get(key) != expected_value for key, expected_value in expected.items()):
        raise ExternalAssuranceError("provider evidence receipt does not match its request")
    return verify_signed_external_receipt(
        receipt,
        verifier=verifier,
        authority_field="provider_id",
    )


@dataclass(frozen=True, slots=True)
class ExternalQualificationDecision:
    external_evidence_status: str
    certification_status: CertificationStatus
    receipt_digests: Mapping[str, str]
    blockers: tuple[str, ...] = ()


def verify_external_qualification_chain(
    *,
    provider_request: ProviderEvidenceRequest,
    provider_receipt: Mapping[str, Any],
    training_request: ExternalRunRequest,
    training_receipt: Mapping[str, Any],
    deployment_request: ExternalRunRequest,
    deployment_receipt: Mapping[str, Any],
    acceptance_request: IndependentAcceptanceRequest,
    acceptance_receipt: Mapping[str, Any],
    certification_request: CertificationRequest,
    certification_receipt: Mapping[str, Any] | None,
    trust_store: ExternalTrustStore,
    now: int,
) -> ExternalQualificationDecision:
    """Verify the complete external chain in dependency order."""

    try:
        scoped_requests = (
            training_request,
            deployment_request,
            acceptance_request,
            certification_request,
        )
        if len({(row.tenant_id, row.project_id) for row in scoped_requests}) != 1:
            raise ExternalAssuranceError(
                "external qualification requests cross tenant or project boundaries"
            )
        if (
            acceptance_request.target_id != deployment_request.target_id
            or certification_request.target_id != deployment_request.target_id
        ):
            raise ExternalAssuranceError(
                "acceptance and certification must target the verified deployment"
            )
        if len({row.producer_id for row in scoped_requests}) != 1:
            raise ExternalAssuranceError("external qualification requests do not bind one producer")
        if acceptance_request.executor_ids != certification_request.executor_ids:
            raise ExternalAssuranceError(
                "acceptance and certification requests bind different executors"
            )
        provider_digest = verify_provider_evidence_receipt(
            provider_request,
            provider_receipt,
            verifier=trust_store.verifier("PROVIDER", now=now),
        )
        training_digest = verify_external_run_receipt(
            training_request,
            training_receipt,
            verifier=trust_store.verifier("TRAINING_PROVIDER", now=now),
        )
        deployment_digest = verify_external_run_receipt(
            deployment_request,
            deployment_receipt,
            verifier=trust_store.verifier("DEPLOYMENT_PROVIDER", now=now),
        )
        executor_ids = {
            require_identifier(training_receipt.get("executor_id"), "executor_id"),
            require_identifier(deployment_receipt.get("executor_id"), "executor_id"),
        }
        if executor_ids != set(acceptance_request.executor_ids):
            raise ExternalAssuranceError(
                "acceptance request does not bind the verified external executors"
            )
        training_finished = training_receipt.get("finished_at")
        deployment_started = deployment_receipt.get("started_at")
        deployment_finished = deployment_receipt.get("finished_at")
        if (
            not isinstance(training_finished, int)
            or isinstance(training_finished, bool)
            or not isinstance(deployment_started, int)
            or isinstance(deployment_started, bool)
            or not isinstance(deployment_finished, int)
            or isinstance(deployment_finished, bool)
            or training_finished > deployment_started
            or deployment_finished > now
        ):
            raise ExternalAssuranceError(
                "training and deployment receipts are future-dated or out of order"
            )
        external_digests = {
            "DEPLOYMENT": deployment_digest,
            "PROVIDER": provider_digest,
            "TRAINING": training_digest,
        }
        if dict(acceptance_request.external_receipt_digests) != external_digests:
            raise ExternalAssuranceError("acceptance request does not bind the verified receipts")
        acceptance_digest = verify_independent_acceptance(
            acceptance_request,
            acceptance_receipt,
            verifier=trust_store.verifier("INDEPENDENT_VERIFIER", now=now),
        )
        if acceptance_receipt.get("verifier_id") != certification_request.independent_verifier_id:
            raise ExternalAssuranceError(
                "certification request does not bind the verified independent authority"
            )
        if (
            dict(certification_request.external_receipt_digests) != external_digests
            or certification_request.independent_acceptance_digest != acceptance_digest
        ):
            raise ExternalAssuranceError("certification request does not bind the verified chain")
        if (
            certification_receipt is not None
            and certification_receipt.get("trust_epoch") != trust_store.trust_epoch
        ):
            raise ExternalAssuranceError("certification receipt trust epoch is stale")
        certification = evaluate_certification(
            certification_request,
            certification_receipt,
            verifier=trust_store.verifier("CERTIFICATION_AUTHORITY", now=now),
            now=now,
        )
        if certification.status is not CertificationStatus.CERTIFIED:
            return ExternalQualificationDecision(
                "VERIFIED_INDEPENDENT",
                CertificationStatus.NOT_CERTIFIED,
                MappingProxyType({**external_digests, "INDEPENDENT_ACCEPTANCE": acceptance_digest}),
                certification.blockers,
            )
        assert certification.receipt_digest is not None
        return ExternalQualificationDecision(
            "VERIFIED_INDEPENDENT",
            CertificationStatus.CERTIFIED,
            MappingProxyType(
                {
                    **external_digests,
                    "INDEPENDENT_ACCEPTANCE": acceptance_digest,
                    "CERTIFICATION": certification.receipt_digest,
                }
            ),
        )
    except (TypeError, ValueError, ExternalAssuranceError) as exc:
        return ExternalQualificationDecision(
            "REJECTED",
            CertificationStatus.NOT_CERTIFIED,
            MappingProxyType({}),
            (str(exc),),
        )


__all__ = [
    "ExternalQualificationDecision",
    "ExternalTrustKey",
    "ExternalTrustStore",
    "ProviderEvidenceRequest",
    "SignatureBackend",
    "verify_external_qualification_chain",
    "verify_provider_evidence_receipt",
]
