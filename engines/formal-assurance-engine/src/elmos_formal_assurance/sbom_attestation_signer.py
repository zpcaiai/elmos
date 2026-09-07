"""Digest-bound CycloneDX and provenance construction with honest claims.

The module never invents component hashes, artifact bytes, builder identity,
reproducibility, SLSA levels or external signatures. A local HMAC signer is
available only as explicitly labelled self-attested engineering evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence

from .canonical import canonical_json, digest_bytes, validate_digest, validate_identifier


class AttestationError(ValueError):
    """Raised when an SBOM or provenance request lacks trusted bindings."""


_UTC_TIMESTAMP = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T"
    r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ$"
)


@dataclass(frozen=True)
class SbomComponent:
    name: str
    version: str
    purl: str
    component_type: str
    hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        _required_text(self.name, "component.name")
        _required_text(self.version, "component.version")
        _required_text(self.purl, "component.purl")
        if not self.purl.startswith("pkg:"):
            raise AttestationError("component.purl must be a package URL")
        if self.component_type not in {
            "application",
            "container",
            "device",
            "file",
            "firmware",
            "framework",
            "library",
            "operating-system",
        }:
            raise AttestationError("component.component_type is invalid")
        if not isinstance(self.hashes, Mapping) or set(self.hashes) != {"SHA-256"}:
            raise AttestationError("component.hashes must contain an exact SHA-256")
        validate_digest(self.hashes["SHA-256"], "component.hashes.SHA-256")

    def to_cyclonedx(self) -> dict[str, Any]:
        return {
            "type": self.component_type,
            "name": self.name,
            "version": self.version,
            "purl": self.purl,
            "hashes": [
                {
                    "alg": "SHA-256",
                    "content": validate_digest(
                        self.hashes["SHA-256"], "component.hashes.SHA-256"
                    ).removeprefix("sha256:"),
                }
            ],
        }


@dataclass(frozen=True)
class AttestationSignature:
    algorithm: str
    key_id: str
    value: str
    classification: str


class AttestationSigner(Protocol):
    def sign(self, payload: bytes) -> AttestationSignature: ...


class HmacLocalAttestationSigner:
    """Local integrity signer; never represented as an independent signature."""

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if not isinstance(key, bytes) or len(key) < 32:
            raise AttestationError("local attestation key must contain at least 32 bytes")
        if len(key) > 4096:
            raise AttestationError("local attestation key exceeds the size bound")
        self._key = bytes(key)
        self._key_id = validate_identifier(key_id, "attestation.keyId")

    def sign(self, payload: bytes) -> AttestationSignature:
        if not isinstance(payload, bytes) or not payload:
            raise AttestationError("attestation payload must be non-empty bytes")
        value = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return AttestationSignature(
            algorithm="HMAC-SHA256",
            key_id=self._key_id,
            value="hmac-sha256:" + value,
            classification="LOCAL_EXECUTED_SELF_ATTESTED",
        )

    def verify(self, payload: bytes, signature: AttestationSignature) -> bool:
        if (
            signature.algorithm != "HMAC-SHA256"
            or signature.key_id != self._key_id
            or signature.classification != "LOCAL_EXECUTED_SELF_ATTESTED"
        ):
            return False
        return hmac.compare_digest(self.sign(payload).value, signature.value)


@dataclass(frozen=True)
class SlsaProvenanceStatement:
    statement: Mapping[str, Any]
    statement_digest: str
    signature: AttestationSignature | None
    signing_status: str
    evidence_classification: str
    issued_at: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["signature"] = asdict(self.signature) if self.signature else None
        return value


class SbomAttestationSigner:
    """Construct exact SBOM/provenance documents and optionally sign locally."""

    def __init__(self, signer: AttestationSigner | None = None) -> None:
        if signer is not None and not callable(getattr(signer, "sign", None)):
            raise AttestationError("attestation signer must implement sign")
        self.signer = signer

    def generate_cyclonedx_sbom(
        self,
        *,
        artifact_name: str,
        artifact_version: str,
        artifact_digest: str,
        components: Sequence[SbomComponent],
        issued_at: str,
    ) -> dict[str, Any]:
        name = _required_text(artifact_name, "artifact_name")
        version = _required_text(artifact_version, "artifact_version")
        digest = validate_digest(artifact_digest, "artifact_digest")
        timestamp = _timestamp(issued_at)
        checked_components = _components(components)
        serial = uuid.uuid5(uuid.NAMESPACE_URL, f"elmos:{name}:{digest}")
        document = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{serial}",
            "version": 1,
            "metadata": {
                "timestamp": timestamp,
                "component": {
                    "type": "application",
                    "name": name,
                    "version": version,
                    "hashes": [
                        {
                            "alg": "SHA-256",
                            "content": digest.removeprefix("sha256:"),
                        }
                    ],
                },
                "tools": {
                    "components": [
                        {
                            "type": "application",
                            "name": "elmos-formal-assurance-engine",
                            "version": "1.0.0",
                        }
                    ]
                },
            },
            "components": [item.to_cyclonedx() for item in checked_components],
        }
        document["properties"] = [
            {
                "name": "elmos:coreDocumentDigest",
                "value": digest_bytes(canonical_json(document)),
            },
            {"name": "elmos:evidenceClassification", "value": "LOCAL_DOCUMENT_GENERATED"},
        ]
        return document

    def sign_slsa_provenance(
        self,
        *,
        artifact_name: str,
        artifact_digest: str,
        builder_id: str,
        build_type: str,
        invocation_digest: str,
        environment_digest: str,
        materials: Sequence[Mapping[str, Any]],
        issued_at: str,
    ) -> SlsaProvenanceStatement:
        name = _required_text(artifact_name, "artifact_name")
        subject_digest = validate_digest(artifact_digest, "artifact_digest")
        builder = _required_text(builder_id, "builder_id")
        kind = _required_text(build_type, "build_type")
        invocation = validate_digest(invocation_digest, "invocation_digest")
        environment = validate_digest(environment_digest, "environment_digest")
        timestamp = _timestamp(issued_at)
        dependencies = _materials(materials)
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": name,
                    "digest": {"sha256": subject_digest.removeprefix("sha256:")},
                }
            ],
            "predicateType": "https://slsa.dev/provenance/v1",
            "predicate": {
                "buildDefinition": {
                    "buildType": kind,
                    "externalParameters": {"invocationDigest": invocation},
                    "internalParameters": {},
                    "resolvedDependencies": dependencies,
                },
                "runDetails": {
                    "builder": {"id": builder},
                    "metadata": {
                        "invocationId": invocation,
                        "startedOn": timestamp,
                        "finishedOn": timestamp,
                    },
                    "byproducts": [
                        {
                            "name": "elmos-environment-binding",
                            "content": {"environmentDigest": environment},
                        }
                    ],
                },
            },
        }
        payload = canonical_json(statement)
        signature = self.signer.sign(payload) if self.signer is not None else None
        return SlsaProvenanceStatement(
            statement=statement,
            statement_digest=digest_bytes(payload),
            signature=signature,
            signing_status=(
                "LOCAL_SELF_ATTESTED_SIGNATURE"
                if signature is not None
                else "SIGNATURE_NOT_RUN"
            ),
            evidence_classification=(
                signature.classification
                if signature is not None
                else "LOCAL_DOCUMENT_GENERATED"
            ),
            issued_at=timestamp,
        )


def sign_artifact_sbom(
    *,
    artifact_name: str,
    artifact_version: str,
    artifact_digest: str,
    components: Sequence[SbomComponent],
    builder_id: str,
    build_type: str,
    invocation_digest: str,
    environment_digest: str,
    materials: Sequence[Mapping[str, Any]],
    issued_at: str,
    signer: AttestationSigner,
    format_type: str = "cyclonedx",
) -> dict[str, Any]:
    """Build and locally sign exact documents; no default key or fake evidence."""
    if format_type.lower() != "cyclonedx":
        raise AttestationError("only CycloneDX 1.5 is supported")
    if signer is None:
        raise AttestationError("an explicit attestation signer is required")
    service = SbomAttestationSigner(signer)
    sbom = service.generate_cyclonedx_sbom(
        artifact_name=artifact_name,
        artifact_version=artifact_version,
        artifact_digest=artifact_digest,
        components=components,
        issued_at=issued_at,
    )
    provenance = service.sign_slsa_provenance(
        artifact_name=artifact_name,
        artifact_digest=artifact_digest,
        builder_id=builder_id,
        build_type=build_type,
        invocation_digest=invocation_digest,
        environment_digest=environment_digest,
        materials=materials,
        issued_at=issued_at,
    )
    return {
        "status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "artifactName": artifact_name,
        "artifactDigest": validate_digest(artifact_digest, "artifact_digest"),
        "format": "cyclonedx-1.5",
        "cycloneDxSbom": sbom,
        "provenance": provenance.to_dict(),
        "slsaLevel": "NOT_ASSESSED",
        "reproducibility": "NOT_RUN",
        "externalSignatureStatus": "NOT_RUN",
        "independentVerificationStatus": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
    }


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise AttestationError(f"{path} must be non-empty text without NUL")
    if len(value.encode("utf-8")) > 4096:
        raise AttestationError(f"{path} exceeds the size bound")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP.fullmatch(value):
        raise AttestationError("issued_at must be an exact UTC second timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise AttestationError(
            "issued_at must be a real Gregorian calendar timestamp"
        ) from exc
    return value


def _components(values: Sequence[SbomComponent]) -> tuple[SbomComponent, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise AttestationError("components must be an array")
    if len(values) > 10_000:
        raise AttestationError("components exceed the item bound")
    if any(not isinstance(item, SbomComponent) for item in values):
        raise AttestationError("components must contain SbomComponent values")
    identities = [(item.purl, item.version) for item in values]
    if len(identities) != len(set(identities)):
        raise AttestationError("components contain duplicate identities")
    return tuple(sorted(values, key=lambda item: (item.purl, item.version)))


def _materials(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise AttestationError("materials must be an array")
    if not values:
        raise AttestationError("at least one provenance material is required")
    if len(values) > 10_000:
        raise AttestationError("materials exceed the item bound")
    result: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, Mapping) or set(value) != {"uri", "sha256"}:
            raise AttestationError(
                f"materials[{index}] must contain exactly uri and sha256"
            )
        uri = _required_text(value["uri"], f"materials[{index}].uri")
        if uri in identities:
            raise AttestationError("materials contain duplicate URIs")
        identities.add(uri)
        digest = validate_digest(value["sha256"], f"materials[{index}].sha256")
        result.append(
            {"uri": uri, "digest": {"sha256": digest.removeprefix("sha256:")}}
        )
    return sorted(result, key=lambda item: item["uri"])


__all__ = [
    "AttestationError",
    "AttestationSignature",
    "AttestationSigner",
    "HmacLocalAttestationSigner",
    "SbomAttestationSigner",
    "SbomComponent",
    "SlsaProvenanceStatement",
    "sign_artifact_sbom",
]
