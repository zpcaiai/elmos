"""Fail-closed provenance verification for certification evidence.

The readiness evaluator consumes ordinary JSON files, which are easy to edit.
This module makes a release decision depend on two Ed25519 attestations over the
exact evidence bytes and policy: one from the executor and one from an
independent verifier.  The trust store is selected and digest-pinned by the
caller; it is deliberately not accepted from inside the evidence directory.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .external_trust import VerifiedExternalTrust

ED25519 = "Ed25519"
SIGNATURE_DOMAIN = "elmos.execution-intelligence.evidence-provenance.v1"
POLICY_NAME = "elmos-execution-intelligence"
POLICY_VERSION = "2.0.0"
REQUIRED_ROLES = ("executor", "independent_verifier")
MAX_CLOCK_SKEW = timedelta(minutes=5)
MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")


class ProvenanceError(ValueError):
    """The supplied provenance cannot support a readiness decision."""


def _reject_json_constant(value: str) -> None:
    raise ProvenanceError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProvenanceError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def load_strict_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    """Parse one captured byte string with security-relevant JSON strictness."""
    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ProvenanceError(f"invalid UTF-8 in {label}") from exc
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError(f"expected a JSON object in {label}")
    return value


def read_regular_file_once(path: str | Path, max_bytes: int = MAX_EVIDENCE_FILE_BYTES) -> bytes:
    """Read one stable regular file descriptor, refusing symlinks and oversize input."""
    source = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ProvenanceError(f"cannot securely open {source}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ProvenanceError(f"evidence input is not a regular file: {source}")
        if before.st_size < 0 or before.st_size > max_bytes:
            raise ProvenanceError(
                f"evidence input exceeds the {max_bytes}-byte limit: {source}"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        stable_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        final_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if stable_identity != final_identity or len(content) != before.st_size:
            raise ProvenanceError(f"evidence input changed while it was being captured: {source}")
        return content
    except OSError as exc:
        raise ProvenanceError(f"cannot read {source}: {exc}") from exc
    finally:
        os.close(descriptor)


def capture_evidence_snapshot(
    evidence_root: str | Path,
    names: Sequence[str],
) -> tuple[dict[str, bytes], list[str]]:
    """Capture every recognized input once; no later gate may reopen it."""
    root = Path(evidence_root).resolve()
    snapshot: dict[str, bytes] = {}
    errors: list[str] = []
    for name in names:
        logical = PurePosixPath(name)
        if logical.as_posix() != name or len(logical.parts) != 1:
            errors.append(f"non-canonical recognized evidence name: {name}")
            continue
        source = root / name
        try:
            os.lstat(source)
        except FileNotFoundError:
            continue
        except OSError as exc:
            errors.append(f"cannot inspect evidence input {name}: {exc}")
            continue
        try:
            snapshot[name] = read_regular_file_once(source)
        except ProvenanceError as exc:
            errors.append(str(exc))
    return snapshot, errors


def canonical_json_bytes(value: Any) -> bytes:
    """RFC-8785-shaped canonical bytes for this integer/string-only contract.

    The signed contract intentionally excludes floating-point values, so sorted
    keys, UTF-8, compact separators and rejected NaN/Infinity are sufficient and
    deterministic across the supported Python versions.
    """
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProvenanceError(f"value cannot be canonicalized: {exc}") from exc
    return encoded.encode("utf-8")


def _require_exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ProvenanceError(f"{label} fields mismatch; missing={missing}, extra={extra}")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
        raise ProvenanceError(f"{label} is not a valid identifier")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProvenanceError(f"{label} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProvenanceError(f"{label} is not a valid timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ProvenanceError(f"{label} must use UTC")
    return parsed.astimezone(timezone.utc)


def _decode_base64(value: Any, expected_size: int, label: str) -> bytes:
    if not isinstance(value, str):
        raise ProvenanceError(f"{label} must be base64 text")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ProvenanceError(f"{label} is not valid base64") from exc
    if len(decoded) != expected_size:
        raise ProvenanceError(f"{label} must decode to exactly {expected_size} bytes")
    return decoded


def _logical_evidence_path(relative: Any) -> str:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ProvenanceError("evidence path must be a non-empty POSIX relative path")
    logical = PurePosixPath(relative)
    if logical.is_absolute() or any(part in {"", ".", ".."} for part in logical.parts):
        raise ProvenanceError(f"unsafe evidence path: {relative}")
    if logical.as_posix() != relative:
        raise ProvenanceError(f"non-canonical evidence path: {relative}")
    return relative


def attestation_payload(provenance: Mapping[str, Any], attestation: Mapping[str, Any]) -> bytes:
    """Return the exact bytes an executor or verifier must sign."""
    header = {
        "key_id": attestation.get("key_id"),
        "role": attestation.get("role"),
        "signed_at": attestation.get("signed_at"),
    }
    payload = {
        "domain": SIGNATURE_DOMAIN,
        "schema_version": provenance.get("schema_version"),
        "artifact": provenance.get("artifact"),
        "issued_at": provenance.get("issued_at"),
        "expires_at": provenance.get("expires_at"),
        "subject": provenance.get("subject"),
        "attestation": header,
    }
    return canonical_json_bytes(payload)


def _verify_ed25519(public_key: bytes, signature: bytes, payload: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - depends on the deployment image
        raise ProvenanceError(
            "Ed25519 verification unavailable; install the declared cryptography dependency"
        ) from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
    except (InvalidSignature, ValueError) as exc:
        raise ProvenanceError("Ed25519 signature verification failed") from exc


def _trust_key_map(trust_store: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    _require_exact_fields(
        trust_store,
        {"schema_version", "artifact", "trust_store_id", "keys"},
        "trust store",
    )
    if trust_store.get("schema_version") != "1.0.0" or trust_store.get("artifact") != "evidence-trust-store":
        raise ProvenanceError("unsupported trust-store contract")
    _identifier(trust_store.get("trust_store_id"), "trust_store_id")
    raw_keys = trust_store.get("keys")
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ProvenanceError("trust store must contain at least one key")
    keys: dict[str, dict[str, Any]] = {}
    expected = {
        "key_id", "principal_id", "organization_id", "authority_id", "role",
        "algorithm", "public_key_base64",
        "not_before", "expires_at", "revoked",
    }
    for index, raw_key in enumerate(raw_keys):
        if not isinstance(raw_key, dict):
            raise ProvenanceError(f"trust store key {index} must be an object")
        _require_exact_fields(raw_key, expected, f"trust store key {index}")
        key_id = _identifier(raw_key.get("key_id"), f"trust store key {index}.key_id")
        _identifier(raw_key.get("principal_id"), f"trust store key {index}.principal_id")
        _identifier(raw_key.get("organization_id"), f"trust store key {index}.organization_id")
        _identifier(raw_key.get("authority_id"), f"trust store key {index}.authority_id")
        if raw_key.get("role") not in REQUIRED_ROLES:
            raise ProvenanceError(f"trust store key {key_id} has an unsupported role")
        if raw_key.get("algorithm") != ED25519:
            raise ProvenanceError(f"trust store key {key_id} is not Ed25519")
        _decode_base64(raw_key.get("public_key_base64"), 32, f"trust store key {key_id}.public_key_base64")
        if not isinstance(raw_key.get("revoked"), bool):
            raise ProvenanceError(f"trust store key {key_id}.revoked must be boolean")
        not_before = _timestamp(raw_key.get("not_before"), f"trust store key {key_id}.not_before")
        expires_at = _timestamp(raw_key.get("expires_at"), f"trust store key {key_id}.expires_at")
        if expires_at <= not_before:
            raise ProvenanceError(f"trust store key {key_id} has an empty validity window")
        if key_id in keys:
            raise ProvenanceError(f"duplicate trust-store key id: {key_id}")
        keys[key_id] = raw_key
    return keys


def _verify_subject(
    subject: Mapping[str, Any],
    evidence_files: Mapping[str, bytes],
    expected_files: Sequence[str],
    min_calibration_samples: int,
) -> list[dict[str, Any]]:
    _require_exact_fields(subject, {"evidence_set_id", "policy", "files"}, "provenance subject")
    _identifier(subject.get("evidence_set_id"), "evidence_set_id")
    expected_policy = {
        "certifier": POLICY_NAME,
        "policy_version": POLICY_VERSION,
        "min_calibration_samples": min_calibration_samples,
        "required_roles": list(REQUIRED_ROLES),
    }
    if subject.get("policy") != expected_policy:
        raise ProvenanceError("signed certification policy does not match the active fail-closed policy")
    raw_files = subject.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ProvenanceError("provenance subject must bind at least one evidence file")
    entries: list[dict[str, Any]] = []
    paths: list[str] = []
    expected_entry_fields = {"path", "sha256", "size_bytes"}
    for index, raw_entry in enumerate(raw_files):
        if not isinstance(raw_entry, dict):
            raise ProvenanceError(f"provenance file {index} must be an object")
        _require_exact_fields(raw_entry, expected_entry_fields, f"provenance file {index}")
        relative = _logical_evidence_path(raw_entry.get("path"))
        digest = raw_entry.get("sha256")
        size = raw_entry.get("size_bytes")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ProvenanceError(f"provenance file {relative} has an invalid SHA-256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ProvenanceError(f"provenance file {relative} has an invalid byte count")
        content = evidence_files.get(relative)
        if content is None:
            raise ProvenanceError(f"signed evidence file was not captured: {relative}")
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            raise ProvenanceError(f"evidence bytes do not match the signed digest and size: {relative}")
        paths.append(relative)
        entries.append({"path": relative, "sha256": digest, "size_bytes": size})
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ProvenanceError("provenance files must be unique and sorted by path")
    if paths != sorted(expected_files):
        raise ProvenanceError(
            "provenance file set must exactly match every recognized evidence input present"
        )
    return entries


def verify_evidence_provenance(
    evidence_root: str | Path,
    trust_store_path: str | Path | None,
    trust_store_sha256: str | None,
    expected_files: Sequence[str],
    min_calibration_samples: int,
    evidence_files: Mapping[str, bytes],
    provenance_bytes: bytes | None,
    snapshot_errors: Sequence[str] = (),
    now: datetime | None = None,
    external_trust: VerifiedExternalTrust | None = None,
    external_trust_error: str | None = None,
) -> dict[str, Any]:
    """Verify digest-bound executor and independent-verifier attestations.

    A structured result is returned for reports. All malformed, missing,
    expired, revoked, role-confused or cryptographically invalid inputs are
    reported as ``FAILED``; callers must never turn that state into PASS.
    """
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, Any] = {
        "status": "FAILED",
        "verified_at": checked_at.isoformat().replace("+00:00", "Z"),
        "errors": [],
        "files": [],
        "signers": [],
    }
    root = Path(evidence_root).resolve()
    try:
        if snapshot_errors:
            raise ProvenanceError("; ".join(snapshot_errors))
        if provenance_bytes is None:
            raise ProvenanceError("evidence-provenance.json is required")
        if external_trust_error is not None:
            raise ProvenanceError(f"external trust authority failed closed: {external_trust_error}")
        if external_trust is not None:
            if trust_store_path is not None or trust_store_sha256 is not None:
                raise ProvenanceError(
                    "static trust-store inputs cannot be combined with an external trust authority"
                )
            trust_store = external_trust.trust_store
            trust_digest = external_trust.trust_store_sha256
        else:
            if trust_store_path is None:
                raise ProvenanceError("an external trust store is required")
            trust_path = Path(trust_store_path).resolve(strict=True)
            try:
                trust_path.relative_to(root)
            except ValueError:
                pass
            else:
                raise ProvenanceError("the trust store must be outside the evidence directory")
            trust_bytes = read_regular_file_once(trust_path)
            if trust_store_sha256 is None or not SHA256_PATTERN.fullmatch(trust_store_sha256):
                raise ProvenanceError("an exact lowercase SHA-256 trust-store pin is required")
            trust_digest = hashlib.sha256(trust_bytes).hexdigest()
            if trust_digest != trust_store_sha256:
                raise ProvenanceError("trust-store digest does not match the caller-provided pin")
            trust_store = load_strict_json_bytes(trust_bytes, str(trust_path))
        keys = _trust_key_map(trust_store)
        provenance = load_strict_json_bytes(provenance_bytes, "evidence-provenance.json")
        _require_exact_fields(
            provenance,
            {"schema_version", "artifact", "issued_at", "expires_at", "subject", "attestations"},
            "evidence provenance",
        )
        if provenance.get("schema_version") != "1.0.0" or provenance.get("artifact") != "evidence-provenance":
            raise ProvenanceError("unsupported evidence-provenance contract")
        issued_at = _timestamp(provenance.get("issued_at"), "provenance.issued_at")
        expires_at = _timestamp(provenance.get("expires_at"), "provenance.expires_at")
        if expires_at <= issued_at:
            raise ProvenanceError("evidence provenance has an empty validity window")
        if checked_at + MAX_CLOCK_SKEW < issued_at:
            raise ProvenanceError("evidence provenance is issued in the future")
        if checked_at > expires_at:
            raise ProvenanceError("evidence provenance has expired")
        subject = provenance.get("subject")
        if not isinstance(subject, dict):
            raise ProvenanceError("provenance subject must be an object")
        bound_files = _verify_subject(
            subject,
            evidence_files,
            expected_files,
            min_calibration_samples,
        )
        raw_attestations = provenance.get("attestations")
        if not isinstance(raw_attestations, list) or len(raw_attestations) != len(REQUIRED_ROLES):
            raise ProvenanceError("exactly one executor and one independent verifier attestation are required")
        signer_records: list[dict[str, Any]] = []
        seen_roles: set[str] = set()
        seen_keys: set[str] = set()
        expected_attestation_fields = {"role", "key_id", "signed_at", "signature"}
        for index, raw_attestation in enumerate(raw_attestations):
            if not isinstance(raw_attestation, dict):
                raise ProvenanceError(f"attestation {index} must be an object")
            _require_exact_fields(raw_attestation, expected_attestation_fields, f"attestation {index}")
            role = raw_attestation.get("role")
            if role not in REQUIRED_ROLES or not isinstance(role, str):
                raise ProvenanceError(f"attestation {index} has an unsupported role")
            key_id = _identifier(raw_attestation.get("key_id"), f"attestation {index}.key_id")
            if role in seen_roles or key_id in seen_keys:
                raise ProvenanceError("attestation roles and keys must be unique")
            seen_roles.add(role)
            seen_keys.add(key_id)
            key = keys.get(key_id)
            if key is None:
                raise ProvenanceError(f"attestation key is not trusted: {key_id}")
            if key.get("role") != role:
                raise ProvenanceError(f"attestation role does not match trusted key role: {key_id}")
            if key.get("revoked") is True:
                raise ProvenanceError(f"attestation key is revoked: {key_id}")
            if external_trust is not None:
                revocation = external_trust.revocations.get(key_id)
                if revocation is None:
                    raise ProvenanceError(
                        f"external revocation authority returned no status for key: {key_id}"
                    )
                revocation_status = revocation.get("status")
                if revocation_status == "REVOKED":
                    raise ProvenanceError(f"external revocation authority revoked key: {key_id}")
                if revocation_status != "GOOD":
                    raise ProvenanceError(
                        f"external revocation status is not GOOD for key {key_id}: "
                        f"{revocation_status}"
                    )
            signed_at = _timestamp(raw_attestation.get("signed_at"), f"attestation {index}.signed_at")
            key_not_before = _timestamp(key.get("not_before"), f"trust key {key_id}.not_before")
            key_expires_at = _timestamp(key.get("expires_at"), f"trust key {key_id}.expires_at")
            if not (issued_at <= signed_at <= expires_at):
                raise ProvenanceError(f"attestation {key_id} is outside the provenance validity window")
            if not (key_not_before <= signed_at <= key_expires_at):
                raise ProvenanceError(f"attestation {key_id} is outside the key validity window")
            if checked_at > key_expires_at:
                raise ProvenanceError(f"attestation key is expired at verification time: {key_id}")
            if signed_at > checked_at + MAX_CLOCK_SKEW:
                raise ProvenanceError(f"attestation is signed in the future: {key_id}")
            public_key = _decode_base64(
                key.get("public_key_base64"), 32, f"trust key {key_id}.public_key_base64"
            )
            signature = _decode_base64(
                raw_attestation.get("signature"), 64, f"attestation {key_id}.signature"
            )
            _verify_ed25519(public_key, signature, attestation_payload(provenance, raw_attestation))
            signer_records.append({
                "role": role,
                "key_id": key_id,
                "principal_id": key["principal_id"],
                "organization_id": key["organization_id"],
                "authority_id": key["authority_id"],
                "signed_at": raw_attestation["signed_at"],
            })
        if seen_roles != set(REQUIRED_ROLES):
            raise ProvenanceError("both executor and independent verifier roles are required")
        independence_fields = ("principal_id", "organization_id", "authority_id")
        for field in independence_fields:
            identities = {record[field] for record in signer_records}
            if len(identities) != len(REQUIRED_ROLES):
                raise ProvenanceError(
                    "executor and independent verifier must have different " + field
                )
        if external_trust is not None:
            trust_authority = external_trust.receipt["issuer_id"]
            signer_authorities = {record["authority_id"] for record in signer_records}
            if trust_authority in signer_authorities:
                raise ProvenanceError(
                    "external trust authority must be separate from executor and verifier authorities"
                )
        result.update({
            "status": "VERIFIED",
            "errors": [],
            "evidence_set_id": subject["evidence_set_id"],
            "trust_store_id": trust_store["trust_store_id"],
            "trust_store_sha256": trust_digest,
            "expires_at": provenance["expires_at"],
            "policy": subject["policy"],
            "files": bound_files,
            "signers": sorted(signer_records, key=lambda item: item["role"]),
        })
        if external_trust is not None:
            result["trust_authority"] = external_trust.receipt
    except (OSError, ProvenanceError) as exc:
        result["errors"] = [str(exc)]
    return result
