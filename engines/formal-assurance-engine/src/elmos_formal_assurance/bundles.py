from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Protocol
from urllib.parse import quote

from .artifact_store import ArtifactStore
from .canonical import (
    canonical_json,
    digest_bytes,
    digest_value,
    validate_digest,
    validate_identifier,
)
from .contracts import Scope, TrustedIdentity, utc_now
from .store import StateStore


class EvidenceBundleError(ValueError):
    """Raised when a bundle cannot be built or verified safely."""


class EvidenceBundleSigner(Protocol):
    def sign(self, payload: bytes) -> dict[str, str]: ...

    def verify(self, payload: bytes, signature: dict[str, Any]) -> bool: ...


class HmacEvidenceBundleSigner:
    """Local qualification signer; external asymmetric signing remains separate."""

    def __init__(self, key: bytes, *, key_id: str = "local-qualification") -> None:
        if not isinstance(key, bytes) or not 32 <= len(key) <= 4096:
            raise EvidenceBundleError("bundle signing key must contain 32-4096 bytes")
        self._key = key
        self.key_id = validate_identifier(key_id, "bundleSigner.keyId")

    def sign(self, payload: bytes) -> dict[str, str]:
        signature = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return {
            "algorithm": "HMAC-SHA256-LOCAL-SELF-ATTESTED",
            "keyId": self.key_id,
            "signature": "hmac-sha256:" + signature,
        }

    def verify(self, payload: bytes, signature: dict[str, Any]) -> bool:
        if signature != {
            "algorithm": "HMAC-SHA256-LOCAL-SELF-ATTESTED",
            "keyId": self.key_id,
            "signature": signature.get("signature"),
        }:
            return False
        value = signature.get("signature")
        if not isinstance(value, str) or not value.startswith("hmac-sha256:"):
            return False
        expected = self.sign(payload)["signature"]
        return hmac.compare_digest(value, expected)


def _redact(value: Any, *, strict: bool) -> Any:
    secret_names = {
        "secret",
        "password",
        "token",
        "credential",
        "apikey",
        "privatekey",
        "authorization",
    }
    strict_names = {"formula", "source", "target", "witness", "content", "body"}
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in secret_names or (strict and normalized in strict_names):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact(item, strict=strict)
        return result
    if isinstance(value, list):
        return [_redact(item, strict=strict) for item in value]
    return value


def _path_component(value: str) -> str:
    validated = validate_identifier(value, "bundlePathComponent")
    encoded = quote(validated, safe="-._")
    if not encoded or encoded in {".", ".."} or "/" in encoded:
        raise EvidenceBundleError("evidence bundle path component is unsafe")
    return encoded


class EvidenceBundleService:
    """Content-addressed, scope-bound evidence bundle build and replay service."""

    def __init__(
        self,
        store: StateStore,
        artifact_store: ArtifactStore | None,
        signer: EvidenceBundleSigner | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.signer = signer

    def build(
        self,
        scope: Scope,
        identity: TrustedIdentity,
        *,
        subject_id: str,
        redaction_policy: str,
        sign: bool,
    ) -> dict[str, Any]:
        del identity  # trusted transport scope is the authorization boundary
        subject_id = validate_identifier(subject_id, "subjectId")
        if redaction_policy not in {"STRICT", "TENANT_INTERNAL"}:
            raise EvidenceBundleError(
                "redactionPolicy must be STRICT or TENANT_INTERNAL"
            )
        if not isinstance(sign, bool):
            raise EvidenceBundleError("sign must be boolean")
        if self.artifact_store is None:
            raise EvidenceBundleError(
                "content-addressed artifact store is not configured"
            )
        documents = self.store.list_documents(scope, subject_id=subject_id)
        documents = [
            record
            for record in documents
            if record["documentType"]
            not in {"evidence_bundle", "evidence_bundle_verification"}
        ]
        if not documents:
            raise EvidenceBundleError(
                "no scope-bound evidence documents exist for subject"
            )
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in documents:
            path = (
                f"documents/{_path_component(record['documentType'])}/"
                f"{_path_component(record['documentId'])}/"
                f"{_path_component(record['version'])}.json"
            )
            if path in seen:
                raise EvidenceBundleError("duplicate evidence bundle path")
            seen.add(path)
            document = _redact(
                record,
                strict=redaction_policy == "STRICT",
            )
            data = canonical_json(document) + b"\n"
            artifact = self.artifact_store.put(
                scope.tenant_id,
                data,
                media_type="application/json",
                retention_class="AUDIT",
            )
            entries.append(
                {
                    "path": path,
                    "sha256": digest_bytes(data),
                    "sizeBytes": len(data),
                    "mediaType": "application/json",
                    "artifactUri": artifact["uri"],
                }
            )
        entries.sort(key=lambda item: item["path"])
        unsigned = {
            "format": "elmos-proof-evidence-bundle/v1",
            "subjectId": subject_id,
            "scopeDigest": digest_value(scope.to_dict()),
            "sourceArtifactDigest": scope.source_artifact_digest,
            "targetArtifactDigest": scope.target_artifact_digest,
            "environmentDigest": scope.environment_digest,
            "redactionPolicy": redaction_policy,
            "files": entries,
            "replay": {
                "environmentDigest": scope.environment_digest,
                "status": "LOCAL_REPLAY_INPUTS_MATERIALIZED",
            },
        }
        manifest: dict[str, Any] = {
            **unsigned,
            "manifestSha256": digest_value(unsigned),
        }
        signature_status = "NOT_REQUESTED"
        if sign and self.signer is not None:
            manifest["signature"] = self.signer.sign(canonical_json(manifest))
            signature_status = "LOCAL_SELF_ATTESTED"
        elif sign:
            signature_status = "NOT_RUN"
        manifest_data = canonical_json(manifest) + b"\n"
        manifest_artifact = self.artifact_store.put(
            scope.tenant_id,
            manifest_data,
            media_type="application/vnd.elmos.proof-evidence-manifest+json",
            retention_class="AUDIT",
        )
        descriptor_unsigned = {
            "format": "elmos-proof-evidence-bundle-descriptor/v1",
            "subjectId": subject_id,
            "scopeDigest": digest_value(scope.to_dict()),
            "manifestRef": manifest_artifact,
            "manifestSha256": digest_bytes(manifest_data),
            "signatureRequested": sign,
            "signatureStatus": signature_status,
            "fileCount": len(entries),
            "createdAt": utc_now(),
        }
        bundle_id = (
            "bundle-" + digest_value(descriptor_unsigned).removeprefix("sha256:")[:32]
        )
        descriptor = {**descriptor_unsigned, "bundleId": bundle_id}
        registration = self.store.put_document(
            scope,
            "evidence_bundle",
            bundle_id,
            descriptor,
            version=f"v{time.time_ns()}",
        )
        return {
            **descriptor,
            "registration": registration,
            "externalEvidenceStatus": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    def verify(self, scope: Scope, *, bundle_id: str) -> dict[str, Any]:
        bundle_id = validate_identifier(bundle_id, "bundleId")
        if self.artifact_store is None:
            raise EvidenceBundleError(
                "content-addressed artifact store is not configured"
            )
        stored = self.store.get_document(scope, "evidence_bundle", bundle_id)
        descriptor = stored["document"]
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("format") != "elmos-proof-evidence-bundle-descriptor/v1"
            or descriptor.get("bundleId") != bundle_id
            or descriptor.get("scopeDigest") != digest_value(scope.to_dict())
        ):
            raise EvidenceBundleError("evidence bundle descriptor is invalid")
        manifest_ref = descriptor.get("manifestRef")
        if not isinstance(manifest_ref, dict):
            raise EvidenceBundleError("evidence bundle manifest reference is invalid")
        manifest_digest = validate_digest(
            manifest_ref.get("sha256"), "manifestRef.sha256"
        )
        manifest_data = self.artifact_store.get(scope.tenant_id, manifest_digest)
        errors: list[str] = []
        if digest_bytes(manifest_data) != descriptor.get("manifestSha256"):
            errors.append("descriptor manifest digest mismatch")
        try:
            import json

            manifest = json.loads(manifest_data)
        except (UnicodeDecodeError, ValueError) as exc:
            raise EvidenceBundleError(
                "evidence bundle manifest is invalid JSON"
            ) from exc
        if not isinstance(manifest, dict):
            raise EvidenceBundleError("evidence bundle manifest must be an object")
        signature = manifest.get("signature")
        unsigned_manifest = {
            key: value for key, value in manifest.items() if key != "signature"
        }
        unsigned = {
            key: value
            for key, value in unsigned_manifest.items()
            if key != "manifestSha256"
        }
        if manifest.get("format") != "elmos-proof-evidence-bundle/v1":
            errors.append("manifest format mismatch")
        if manifest.get("scopeDigest") != digest_value(scope.to_dict()):
            errors.append("manifest scope mismatch")
        if manifest.get("manifestSha256") != digest_value(unsigned):
            errors.append("manifest hash mismatch")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries:
            errors.append("manifest files are missing")
            entries = []
        paths: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"file {index}: invalid entry")
                continue
            path = entry.get("path")
            if (
                not isinstance(path, str)
                or not path
                or path.startswith("/")
                or ".." in path.split("/")
            ):
                errors.append(f"file {index}: unsafe path")
                continue
            if path in paths:
                errors.append(f"file {index}: duplicate path")
                continue
            paths.add(path)
            try:
                digest = validate_digest(entry.get("sha256"), f"file[{index}].sha256")
                data = self.artifact_store.get(scope.tenant_id, digest)
            except (ValueError, OSError) as exc:
                errors.append(f"file {index}: {exc}")
                continue
            if digest_bytes(data) != digest:
                errors.append(f"file {index}: digest mismatch")
            if entry.get("sizeBytes") != len(data):
                errors.append(f"file {index}: size mismatch")
        if signature is None:
            signature_status = (
                "NOT_RUN" if descriptor.get("signatureRequested") else "NOT_REQUESTED"
            )
            if descriptor.get("signatureRequested"):
                errors.append("requested bundle signature is missing")
        elif self.signer is None:
            signature_status = "UNVERIFIED_SIGNER_UNAVAILABLE"
            errors.append("bundle signer is unavailable for verification")
        elif not isinstance(signature, dict) or not self.signer.verify(
            canonical_json(unsigned_manifest), signature
        ):
            signature_status = "INVALID"
            errors.append("bundle signature verification failed")
        else:
            signature_status = "LOCAL_SELF_ATTESTED_VERIFIED"
        integrity_status = "VERIFIED" if not errors else "FAILED"
        result = {
            "bundleId": bundle_id,
            "integrityStatus": integrity_status,
            "signatureStatus": signature_status,
            "fileCount": len(entries),
            "errors": errors,
            "offlineReplayInputsVerified": not errors,
            "externalEvidenceStatus": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "verifiedAt": utc_now(),
        }
        self.store.put_document(
            scope,
            "evidence_bundle_verification",
            bundle_id,
            result,
            version=f"v{time.time_ns()}",
        )
        return result


__all__ = [
    "EvidenceBundleError",
    "EvidenceBundleService",
    "EvidenceBundleSigner",
    "HmacEvidenceBundleSigner",
]
