"""Independent Ed25519 attestation verification for ETGB release gates.

The runtime verifies evidence produced by a separate executor/verifier. It does
not create a release certificate, accept a boolean "attested" claim, or store
private key material.
"""

from __future__ import annotations

import base64
import binascii
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_json, digest_json


class AttestationError(ValueError):
    """Raised when an attestation or trust record is malformed."""


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{1,127}$")
_ATTESTATION_FIELDS = frozenset({
    "schema_version", "attestation_id", "profile", "subject", "executor_id",
    "verifier_id", "issued_at", "expires_at", "key_id", "algorithm", "signature",
})
_SUBJECT_FIELDS = frozenset({
    "candidate_digest", "score_digest", "validation_digest", "coverage_digest",
    "corpus_digest", "evidence_digest",
})


def _decode_base64url(value: Any, *, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AttestationError(f"{field} must be a non-empty base64url string")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as exc:
        raise AttestationError(f"{field} is not valid base64url") from exc


def _parse_time(value: Any, *, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise AttestationError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AttestationError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AttestationError(f"{field} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def unsigned_payload(attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical signed payload, excluding only the signature."""

    return {key: attestation[key] for key in sorted(attestation) if key != "signature"}


def validate_attestation_structure(attestation: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(attestation, Mapping):
        return ["attestation must be an object"]
    missing = _ATTESTATION_FIELDS - set(attestation)
    extra = set(attestation) - _ATTESTATION_FIELDS
    errors.extend(f"missing attestation field: {field}" for field in sorted(missing))
    errors.extend(f"unexpected attestation field: {field}" for field in sorted(extra))
    for field in ("attestation_id", "executor_id", "verifier_id", "key_id"):
        if field in attestation and (not isinstance(attestation[field], str) or not _IDENTIFIER.fullmatch(attestation[field])):
            errors.append(f"{field} is not a valid identifier")
    if attestation.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if attestation.get("profile") not in {"release", "golden"}:
        errors.append("profile must be release or golden")
    if attestation.get("algorithm") != "ed25519":
        errors.append("algorithm must be ed25519")
    if attestation.get("executor_id") == attestation.get("verifier_id"):
        errors.append("executor and verifier identities must be separate")
    subject = attestation.get("subject")
    if not isinstance(subject, Mapping):
        errors.append("subject must be an object")
    else:
        errors.extend(f"missing subject field: {field}" for field in sorted(_SUBJECT_FIELDS - set(subject)))
        errors.extend(f"unexpected subject field: {field}" for field in sorted(set(subject) - _SUBJECT_FIELDS))
        for field in sorted(_SUBJECT_FIELDS):
            if field in subject and (not isinstance(subject[field], str) or not _DIGEST.fullmatch(subject[field])):
                errors.append(f"subject.{field} must be a lowercase SHA-256 digest")
    try:
        issued = _parse_time(attestation.get("issued_at"), field="issued_at")
        expires = _parse_time(attestation.get("expires_at"), field="expires_at")
        if expires <= issued:
            errors.append("expires_at must be after issued_at")
    except AttestationError as exc:
        errors.append(str(exc))
    if "signature" in attestation:
        try:
            if len(_decode_base64url(attestation["signature"], field="signature")) != 64:
                errors.append("signature must decode to 64 bytes")
        except AttestationError as exc:
            errors.append(str(exc))
    return errors


def load_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AttestationError(f"attestation input must be a regular file: {path}")
    resolved = path.resolve(strict=True)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttestationError(f"unable to load JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise AttestationError(f"JSON input must be an object: {path}")
    return value


def _key_record(trust_store: Mapping[str, Any], key_id: str) -> Mapping[str, Any]:
    if trust_store.get("schema_version") != "1.0" or not isinstance(trust_store.get("keys"), list):
        raise AttestationError("trust store must have schema_version 1.0 and a keys list")
    matches = [item for item in trust_store["keys"] if isinstance(item, Mapping) and item.get("key_id") == key_id]
    if len(matches) != 1:
        raise AttestationError(f"trust store must contain exactly one key for {key_id}")
    record = matches[0]
    if record.get("algorithm") != "ed25519" or record.get("status") != "active":
        raise AttestationError(f"trust key {key_id} is not an active Ed25519 key")
    return record


def verify_attestation(attestation: Mapping[str, Any], trust_store: Mapping[str, Any], *, now: dt.datetime | None = None, clock_skew_seconds: int = 300) -> dict[str, Any]:
    """Verify structure, validity window, trust status, and Ed25519 signature."""

    errors = validate_attestation_structure(attestation)
    payload_digest: str | None = None
    if errors:
        return {"valid": False, "errors": errors, "payload_digest": payload_digest}
    issued = _parse_time(attestation["issued_at"], field="issued_at")
    expires = _parse_time(attestation["expires_at"], field="expires_at")
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    if issued - dt.timedelta(seconds=clock_skew_seconds) > current:
        errors.append("attestation is not yet valid")
    if expires <= current:
        errors.append("attestation is expired")
    payload = unsigned_payload(attestation)
    payload_digest = digest_json(payload)
    try:
        record = _key_record(trust_store, str(attestation["key_id"]))
        not_before = _parse_time(record["not_before"], field="trust-key.not_before")
        not_after = _parse_time(record["not_after"], field="trust-key.not_after")
        if not_before > current or not_after <= current:
            errors.append("trust key is outside its validity window")
        public_key = _decode_base64url(record.get("public_key"), field="trust-key.public_key")
        signature = _decode_base64url(attestation["signature"], field="signature")
        if len(public_key) != 32 or len(signature) != 64:
            raise AttestationError("Ed25519 public key/signature length is invalid")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical_json(payload))
        except ImportError as exc:
            raise AttestationError("cryptography package is required for Ed25519 verification") from exc
        except Exception as exc:
            errors.append(f"Ed25519 signature verification failed: {type(exc).__name__}")
    except AttestationError as exc:
        errors.append(str(exc))
    return {
        "valid": not errors,
        "errors": errors,
        "payload_digest": payload_digest,
        "attestation_id": attestation.get("attestation_id"),
        "verifier_id": attestation.get("verifier_id"),
        "key_id": attestation.get("key_id"),
    }


def verify_attestation_binding(
    attestation: Mapping[str, Any],
    trust_store: Mapping[str, Any],
    *,
    candidate_digest: str | None,
    score: Mapping[str, Any],
    validation: Mapping[str, Any],
    coverage: Mapping[str, Any],
    corpus: Mapping[str, Any],
    evidence: Any,
) -> dict[str, Any]:
    """Verify an attestation and bind it to the exact gate inputs."""

    result = verify_attestation(attestation, trust_store)
    if candidate_digest is None or not _DIGEST.fullmatch(candidate_digest):
        result["valid"] = False
        result.setdefault("errors", []).append("candidate_digest is required to verify release binding")
    expected = {
        "candidate_digest": candidate_digest,
        "score_digest": digest_json(score),
        "validation_digest": digest_json(validation),
        "coverage_digest": digest_json(coverage),
        "corpus_digest": digest_json(corpus),
        "evidence_digest": digest_json(evidence),
    }
    subject = attestation.get("subject", {}) if isinstance(attestation, Mapping) else {}
    if isinstance(subject, Mapping):
        for field, value in expected.items():
            if value is not None and subject.get(field) != value:
                result["valid"] = False
                result.setdefault("errors", []).append(f"attestation subject mismatch: {field}")
    return result


def evidence_binding(results: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a stable case-id/manifest projection for release attestation."""

    return [
        {"case_id": str(result.get("case_id")), "manifest": result.get("evidence", {}).get("manifest")}
        for result in sorted(results, key=lambda item: str(item.get("case_id")))
    ]


def verify_signed_record(record: Mapping[str, Any], trust_store: Mapping[str, Any], *, record_type: str, now: dt.datetime | None = None, clock_skew_seconds: int = 300) -> dict[str, Any]:
    """Verify a generic signed governance record without accepting extra fields."""

    required = {"schema_version", "record_type", "payload", "issuer_id", "key_id", "algorithm", "issued_at", "expires_at", "signature"}
    errors: list[str] = []
    if not isinstance(record, Mapping):
        return {"valid": False, "errors": ["signed record must be an object"]}
    errors.extend(f"missing signed-record field: {field}" for field in sorted(required - set(record)))
    errors.extend(f"unexpected signed-record field: {field}" for field in sorted(set(record) - required))
    if record.get("schema_version") != "1.0":
        errors.append("signed-record schema_version must be 1.0")
    if record.get("record_type") != record_type:
        errors.append(f"signed-record record_type must be {record_type}")
    if not isinstance(record.get("payload"), Mapping):
        errors.append("signed-record payload must be an object")
    for field in ("issuer_id", "key_id"):
        if not isinstance(record.get(field), str) or not _IDENTIFIER.fullmatch(record[field]):
            errors.append(f"signed-record {field} is not a valid identifier")
    if record.get("algorithm") != "ed25519":
        errors.append("signed-record algorithm must be ed25519")
    try:
        issued = _parse_time(record.get("issued_at"), field="signed-record.issued_at")
        expires = _parse_time(record.get("expires_at"), field="signed-record.expires_at")
        current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
        if expires <= issued:
            errors.append("signed-record expires_at must be after issued_at")
        if issued - dt.timedelta(seconds=clock_skew_seconds) > current:
            errors.append("signed-record is not yet valid")
        if expires <= current:
            errors.append("signed-record is expired")
    except AttestationError as exc:
        errors.append(str(exc))
        current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    try:
        signature = _decode_base64url(record.get("signature"), field="signed-record.signature")
        key = _key_record(trust_store, str(record.get("key_id")))
        not_before = _parse_time(key["not_before"], field="trust-key.not_before")
        not_after = _parse_time(key["not_after"], field="trust-key.not_after")
        if not_before > current or not_after <= current:
            errors.append("trust key is outside its validity window")
        public_key = _decode_base64url(key.get("public_key"), field="trust-key.public_key")
        if len(public_key) != 32 or len(signature) != 64:
            raise AttestationError("Ed25519 public key/signature length is invalid")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical_json(unsigned_payload(record)))
        except ImportError as exc:
            raise AttestationError("cryptography package is required for Ed25519 verification") from exc
        except Exception as exc:
            errors.append(f"Ed25519 signed-record verification failed: {type(exc).__name__}")
    except AttestationError as exc:
        errors.append(str(exc))
    return {"valid": not errors, "errors": errors, "payload_digest": digest_json(unsigned_payload(record)), "issuer_id": record.get("issuer_id"), "key_id": record.get("key_id")}
