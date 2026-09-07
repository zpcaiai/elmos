"""Tenant-scoped, independently signed parity evidence verification.

CAS presence alone is not evidence. Production parity decisions require an
authenticated tenant/project scope, a separately authorized evidence object,
tenant artifact registration and references for every byte involved, and an
asymmetric signature from a trusted verifier that is independent of the
executor. Local harness manifests intentionally remain ``NOT_RUN`` external
evidence and therefore cannot prepare the API external gate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .canonical import digest_of, require_digest
from .clock import SYSTEM_CLOCK, Clock
from .parity import EvidenceBinding
from .security import (
    SYMMETRIC_ALGORITHMS,
    ProvenanceSigner,
    SignedStatement,
    require_asymmetric,
)

EVIDENCE_ATTESTATION_KIND = "elmos.cache-parity-evidence-attestation/v1.2"
EVIDENCE_REF_SOURCE_KIND = "parity-evidence-authorization"
EXTERNAL_EVIDENCE_CLASS = "EXTERNAL_RUNTIME"
EXTERNAL_EVIDENCE_STATE = "EXTERNAL_VERIFIED"


class VerifiedCasReader(Protocol):
    def get_bytes(self, digest: str, verify: bool = True) -> bytes: ...


class ArtifactRegistration(Protocol):
    @property
    def tenant_id(self) -> str: ...

    @property
    def digest(self) -> str: ...

    @property
    def size_bytes(self) -> int: ...

    @property
    def storage_state(self) -> Any: ...

    @property
    def validation_level(self) -> Any: ...


class TenantArtifactOwnershipReader(Protocol):
    """Minimal tenant registry contract; ``MetadataStore`` implements it."""

    def get_artifact(self, tenant_id: str, digest: str) -> ArtifactRegistration | None: ...

    def artifact_referrers(self, tenant_id: str, digest: str) -> list[tuple[str, str, str]]: ...


class ParityEvidenceTrustVerifier(Protocol):
    """Externally injectable trust decision for a verifier signature."""

    def verify(
        self,
        signed: SignedStatement,
        *,
        expected_verifier_identity: str,
    ) -> None: ...


class AsymmetricParityEvidenceTrustVerifier:
    """Public-key verifier with an explicit trusted key-to-identity binding."""

    def __init__(
        self,
        verifier: ProvenanceSigner,
        trusted_key_identities: Mapping[str, str],
    ) -> None:
        self.verifier = require_asymmetric(verifier)
        self.trusted_key_identities = dict(trusted_key_identities)
        if not self.trusted_key_identities or any(
            not key_id or not identity
            for key_id, identity in self.trusted_key_identities.items()
        ):
            raise ValueError("trusted parity verifier key identities must be non-empty")

    def verify(
        self,
        signed: SignedStatement,
        *,
        expected_verifier_identity: str,
    ) -> None:
        trusted_identity = self.trusted_key_identities.get(signed.key_id)
        if trusted_identity != expected_verifier_identity:
            raise ValueError("parity evidence key is not trusted for the claimed verifier")
        if signed.algorithm in SYMMETRIC_ALGORITHMS:
            raise ValueError("parity evidence requires an asymmetric signature")
        self.verifier.verify_statement(signed)


@dataclass(frozen=True)
class EvidenceVerification:
    """Closed verification outcome consumed by the parity API."""

    valid: bool
    reason_code: str
    execution_manifest_digest: str | None = None
    attestation_digest: str | None = None


class _EvidenceFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parity_evidence_ref_kind(project_id: str) -> str:
    """Return the exact project-qualified artifact reference required by the verifier."""

    if not isinstance(project_id, str) or not project_id or len(project_id) > 128:
        raise ValueError("project_id must be a bounded non-empty string")
    return f"project:{project_id}"


class CasParityEvidenceVerifier:
    """Verify exact external evidence without trusting caller-supplied claims."""

    def __init__(
        self,
        cas: VerifiedCasReader,
        ownership: TenantArtifactOwnershipReader | None = None,
        trust_verifier: ParityEvidenceTrustVerifier | None = None,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        self.cas = cas
        self.ownership = ownership
        self.trust_verifier = trust_verifier
        self.clock = clock

    def verify_scenario(
        self,
        scenario_id: str,
        evidence_digests: Sequence[str],
        binding: EvidenceBinding,
        metrics: Mapping[str, float | int],
        cohorts: Mapping[str, Mapping[str, float | int]],
        *,
        tenant_id: str,
        project_id: str,
        report_id: str,
    ) -> EvidenceVerification:
        expected_scope = digest_of({"tenant_id": tenant_id, "project_id": project_id})
        if not binding.authenticated or binding.authorization_digest is None:
            return EvidenceVerification(False, "EVIDENCE_SCOPE_OR_AUTHORIZATION_MISSING")
        if binding.tenant_scope_digest != expected_scope:
            return EvidenceVerification(False, "EVIDENCE_SCOPE_MISMATCH")
        if self.ownership is None:
            return EvidenceVerification(False, "EVIDENCE_OWNERSHIP_VERIFIER_UNAVAILABLE")
        if self.trust_verifier is None:
            return EvidenceVerification(False, "EVIDENCE_TRUST_VERIFIER_UNAVAILABLE")
        if not evidence_digests or len(set(evidence_digests)) != len(evidence_digests):
            return EvidenceVerification(False, "EVIDENCE_SET_EMPTY_OR_DUPLICATE")
        submitted = set(evidence_digests)
        if binding.authorization_digest not in submitted:
            return EvidenceVerification(False, "EVIDENCE_AUTHORIZATION_NOT_SUBMITTED")

        raw_objects: dict[str, bytes] = {}
        documents: dict[str, dict[str, Any]] = {}
        try:
            for digest in evidence_digests:
                raw = self._owned_bytes(
                    tenant_id,
                    project_id,
                    binding.authorization_digest,
                    digest,
                )
                raw_objects[digest] = raw
                try:
                    decoded = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(decoded, dict):
                    documents[digest] = decoded
        except _EvidenceFailure as exc:
            return EvidenceVerification(False, exc.code)

        manifests = [
            (digest, document)
            for digest, document in documents.items()
            if document.get("kind") == "elmos.cache-parity-scenario-execution/v1.2"
        ]
        if len(manifests) != 1:
            return EvidenceVerification(False, "SCENARIO_MANIFEST_MISSING_OR_AMBIGUOUS")
        manifest_digest, manifest = manifests[0]
        if (
            manifest.get("schema_version") != "1.2.0"
            or manifest.get("scenario_id") != scenario_id
            or manifest.get("status") != "PASS"
            or manifest.get("executor_identity") != binding.executor_identity
        ):
            return EvidenceVerification(False, "SCENARIO_MANIFEST_BINDING_MISMATCH")
        if (
            manifest.get("evidence_class") != EXTERNAL_EVIDENCE_CLASS
            or manifest.get("external_evidence_state") != EXTERNAL_EVIDENCE_STATE
        ):
            return EvidenceVerification(False, "SCENARIO_EXTERNAL_EVIDENCE_NOT_VERIFIED")

        request = manifest.get("request")
        if not isinstance(request, dict):
            return EvidenceVerification(False, "SCENARIO_REQUEST_MISSING")
        case = request.get("case")
        if (
            request.get("kind") != "elmos.cache-parity-scenario-request/v1.2"
            or request.get("run_id") != report_id
            or request.get("binding") != binding.to_dict()
            or not isinstance(case, dict)
            or case.get("scenario_id") != scenario_id
        ):
            return EvidenceVerification(False, "SCENARIO_REQUEST_BINDING_MISMATCH")
        request_digest = digest_of(request)
        if manifest.get("request_digest") != request_digest:
            return EvidenceVerification(False, "SCENARIO_REQUEST_DIGEST_MISMATCH")
        if not self._valid_replay(
            manifest.get("replay"), request_digest=request_digest, require_attempt=True
        ):
            return EvidenceVerification(False, "SCENARIO_REPLAY_INVALID")
        scenario_raw = self._raw_evidence_digests(manifest.get("raw_evidence"), raw_objects)
        if scenario_raw is None:
            return EvidenceVerification(False, "SCENARIO_RAW_EVIDENCE_INVALID")

        measurement_digest = request.get("measurement_bundle_digest")
        if not isinstance(measurement_digest, str) or measurement_digest not in documents:
            return EvidenceVerification(False, "MEASUREMENT_MANIFEST_MISSING")
        measurement = documents[measurement_digest]
        measurement_raw = self._raw_evidence_digests(
            measurement.get("raw_evidence"), raw_objects
        )
        if (
            measurement.get("kind") != "elmos.cache-parity-measurement-bundle/v1.2"
            or measurement.get("producer_identity") != binding.executor_identity
            or measurement.get("evidence_class") != EXTERNAL_EVIDENCE_CLASS
            or measurement.get("external_evidence_state") != EXTERNAL_EVIDENCE_STATE
            or measurement.get("binding") != binding.to_dict()
            or measurement.get("global_metrics") != dict(metrics)
            or measurement.get("cohorts")
            != {name: dict(values) for name, values in sorted(cohorts.items())}
            or measurement_raw is None
        ):
            return EvidenceVerification(False, "MEASUREMENT_BINDING_MISMATCH")
        if not self._valid_replay(
            measurement.get("replay"), request_digest=None, require_attempt=False
        ):
            return EvidenceVerification(False, "MEASUREMENT_REPLAY_INVALID")

        attestations = [
            (digest, document)
            for digest, document in documents.items()
            if document.get("kind") == EVIDENCE_ATTESTATION_KIND
        ]
        if len(attestations) != 1:
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_MISSING_OR_AMBIGUOUS")
        attestation_digest, attestation_document = attestations[0]
        try:
            signed = self._signed_statement(attestation_document)
        except (KeyError, TypeError, ValueError):
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_INVALID")

        authorized_digests = {
            manifest_digest,
            measurement_digest,
            binding.authorization_digest,
            *scenario_raw,
            *measurement_raw,
        }
        if submitted != authorized_digests | {attestation_digest}:
            return EvidenceVerification(False, "EVIDENCE_SET_NOT_EXACTLY_AUTHORIZED")
        expected_statement = {
            "schema_version": "1.2.0",
            "report_id": report_id,
            "scenario_id": scenario_id,
            "tenant_scope_digest": expected_scope,
            "authorization_digest": binding.authorization_digest,
            "evidence_binding_digest": digest_of(binding.to_dict()),
            "request_digest": request_digest,
            "execution_manifest_digest": manifest_digest,
            "measurement_bundle_digest": measurement_digest,
            "evidence_digests": sorted(authorized_digests),
            "executor_identity": binding.executor_identity,
            "verifier_identity": binding.verifier_identity,
        }
        if not self._statement_matches(signed.statement, expected_statement):
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_BINDING_MISMATCH")
        if not self._valid_time_bounds(signed.statement):
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_EXPIRED_OR_NOT_YET_VALID")
        if signed.algorithm in SYMMETRIC_ALGORITHMS:
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_NOT_ASYMMETRIC")
        try:
            self.trust_verifier.verify(
                signed,
                expected_verifier_identity=binding.verifier_identity,
            )
        except Exception:  # noqa: BLE001 - trust failure is a non-success result
            return EvidenceVerification(False, "EVIDENCE_ATTESTATION_UNTRUSTED")
        return EvidenceVerification(True, "VERIFIED", manifest_digest, attestation_digest)

    def _owned_bytes(
        self,
        tenant_id: str,
        project_id: str,
        authorization_digest: str,
        digest: str,
    ) -> bytes:
        assert self.ownership is not None
        try:
            normalized = require_digest(digest)
            registration = self.ownership.get_artifact(tenant_id, normalized)
            references = self.ownership.artifact_referrers(tenant_id, normalized)
            raw = self.cas.get_bytes(normalized, verify=True)
        except Exception as exc:  # noqa: BLE001 - do not leak cross-tenant existence
            raise _EvidenceFailure("EVIDENCE_OBJECT_UNOWNED_OR_INVALID") from exc
        expected_ref = (
            EVIDENCE_REF_SOURCE_KIND,
            authorization_digest,
            parity_evidence_ref_kind(project_id),
        )
        if (
            registration is None
            or registration.tenant_id != tenant_id
            or registration.digest != normalized
            or registration.size_bytes != len(raw)
            or str(registration.storage_state) not in {"LOCAL", "REMOTE"}
            or str(registration.validation_level) == "QUARANTINED"
            or expected_ref not in references
            or not raw
        ):
            raise _EvidenceFailure("EVIDENCE_OBJECT_UNOWNED_OR_INVALID")
        return raw

    @staticmethod
    def _raw_evidence_digests(
        value: Any,
        raw_objects: Mapping[str, bytes],
    ) -> set[str] | None:
        if not isinstance(value, list) or not value:
            return None
        roles: set[str] = set()
        digests: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                return None
            role = item.get("role")
            digest = item.get("digest")
            size = item.get("size")
            if (
                not isinstance(role, str)
                or not role
                or role in roles
                or not isinstance(digest, str)
                or digest in digests
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 1
                or digest not in raw_objects
                or len(raw_objects[digest]) != size
            ):
                return None
            try:
                require_digest(digest)
            except Exception:  # noqa: BLE001 - untrusted digest fails closed
                return None
            roles.add(role)
            digests.add(digest)
        return digests

    @staticmethod
    def _valid_replay(
        value: Any,
        *,
        request_digest: str | None,
        require_attempt: bool,
    ) -> bool:
        if not isinstance(value, dict):
            return False
        if (
            value.get("protocol") != "elmos.cache-parity-replay/v1.2"
            or not value.get("request_digest")
            or (request_digest is not None and value.get("request_digest") != request_digest)
            or not value.get("runner")
            or not value.get("runner_version")
        ):
            return False
        if not require_attempt:
            return True
        attempt = value.get("attempt")
        return isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1

    @staticmethod
    def _signed_statement(document: Mapping[str, Any]) -> SignedStatement:
        if set(document) != {"kind", "statement", "signature", "key_id", "algorithm"}:
            raise ValueError("signed parity evidence has an unexpected shape")
        signed = SignedStatement.from_dict(document)
        if signed.kind != EVIDENCE_ATTESTATION_KIND:
            raise ValueError("signed parity evidence has an unexpected kind")
        return signed

    @staticmethod
    def _statement_matches(
        statement: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> bool:
        time_fields = {"issued_at", "expires_at"}
        return set(statement) == set(expected) | time_fields and all(
            statement.get(name) == value for name, value in expected.items()
        )

    def _valid_time_bounds(self, statement: Mapping[str, Any]) -> bool:
        issued = statement.get("issued_at")
        expires = statement.get("expires_at")
        if (
            isinstance(issued, bool)
            or not isinstance(issued, int | float)
            or isinstance(expires, bool)
            or not isinstance(expires, int | float)
            or not math.isfinite(float(issued))
            or not math.isfinite(float(expires))
            or float(expires) <= float(issued)
        ):
            return False
        now = self.clock.now()
        return float(issued) - 300.0 <= now < float(expires)


__all__ = [
    "AsymmetricParityEvidenceTrustVerifier",
    "CasParityEvidenceVerifier",
    "EVIDENCE_ATTESTATION_KIND",
    "EVIDENCE_REF_SOURCE_KIND",
    "EvidenceVerification",
    "ParityEvidenceTrustVerifier",
    "TenantArtifactOwnershipReader",
    "VerifiedCasReader",
    "parity_evidence_ref_kind",
]
