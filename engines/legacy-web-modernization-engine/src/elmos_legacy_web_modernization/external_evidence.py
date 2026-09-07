"""Fail-closed intake verification for real legacy-web evidence.

The local modernization runtime is deliberately unable to promote its own
results.  This module is the admission boundary for evidence produced by
separate build, runtime, customer, independent-review, and certification
actors.  It verifies bytes and signatures, but it never mutates a pack or
returns ``CERTIFIED``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_bytes, canonical_digest
from .catalog import EXPECTED_ARCHIVE_SHA256, PACKAGE_NAME, PACKAGE_VERSION


NAMESPACE = "elmos.legacy-web.external-certification"
SCHEMA_VERSION = 1
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

EVIDENCE_TYPES = (
    "source_build",
    "target_build",
    "source_startup",
    "target_startup",
    "behavioral_equivalence",
    "security",
    "performance",
    "operability",
    "sbom",
    "rollback",
    "independent_review",
    "customer_acceptance",
    "external_certification",
)

EVIDENCE_ROLES = {
    "source_build": "legacy-web-source-build-verifier",
    "target_build": "legacy-web-target-build-verifier",
    "source_startup": "legacy-web-source-runtime-verifier",
    "target_startup": "legacy-web-target-runtime-verifier",
    "behavioral_equivalence": "legacy-web-behavior-verifier",
    "security": "legacy-web-security-verifier",
    "performance": "legacy-web-performance-verifier",
    "operability": "legacy-web-operability-verifier",
    "sbom": "legacy-web-sbom-verifier",
    "rollback": "legacy-web-rollback-verifier",
    "independent_review": "legacy-web-independent-reviewer",
    "customer_acceptance": "legacy-web-customer-acceptance-approver",
    "external_certification": "legacy-web-external-certifier",
}

ORGANIZATION_BINDINGS = {
    "source_build": "producer",
    "target_build": "rootless",
    "source_startup": "producer",
    "target_startup": "rootless",
    "behavioral_equivalence": "rootless",
    "security": "independent",
    "performance": "independent",
    "operability": "independent",
    "sbom": "independent",
    "rollback": "independent",
    "independent_review": "independent",
    "customer_acceptance": "customer",
    "external_certification": "certification",
}

CLAIMS = {
    "source_build": {"passed": True, "native": True, "exact_toolchain": True},
    "target_build": {"passed": True, "native": True, "exact_toolchain": True},
    "source_startup": {"passed": True, "native": True, "readiness": True},
    "target_startup": {"passed": True, "native": True, "readiness": True},
    "behavioral_equivalence": {
        "passed": True,
        "critical_mismatch_count": 0,
        "route_coverage": 1.0,
    },
    "security": {"passed": True, "critical_findings": 0},
    "performance": {"passed": True, "capacity_validated": True},
    "operability": {
        "passed": True,
        "endpoints_verified": ["/livez", "/readyz", "/metrics", "/version"],
    },
    "sbom": {"passed": True, "artifact_bound": True},
    "rollback": {"passed": True, "rehearsed": True},
    "independent_review": {
        "passed": True,
        "organizationally_independent": True,
    },
    "customer_acceptance": {"accepted": True, "artifact_bound": True},
    "external_certification": {
        "decision": "CERTIFIED",
        "scope_bound": True,
        "independent_authority": True,
    },
}


class ExternalEvidenceError(ValueError):
    """Raised when an external evidence intake is unsafe or not admissible."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExternalEvidenceError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], required: set[str], label: str) -> None:
    observed = set(value)
    missing = sorted(required - observed)
    extra = sorted(observed - required)
    if missing or extra:
        raise ExternalEvidenceError(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExternalEvidenceError(f"{label} must be a non-empty string")
    return value


def _identity(value: Any, label: str) -> str:
    observed = _text(value, label)
    if IDENTIFIER.fullmatch(observed) is None:
        raise ExternalEvidenceError(f"{label} is not a bounded identity")
    if observed.upper() in {
        "UNKNOWN",
        "NOT_RUN",
        "NOT_EVALUATED",
        "INCONCLUSIVE",
        "BLOCKED",
        "TODO",
    }:
        raise ExternalEvidenceError(f"{label} must not be a non-success sentinel")
    return observed


def _digest(value: Any, label: str) -> str:
    observed = _text(value, label)
    if DIGEST.fullmatch(observed) is None:
        raise ExternalEvidenceError(f"{label} must be sha256:<64 lowercase hex>")
    return observed


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExternalEvidenceError(f"{label} must be a positive integer")
    return value


def _relative_parts(value: Any, label: str) -> tuple[str, ...]:
    observed = _text(value, label)
    candidate = Path(observed)
    if candidate.is_absolute() or not candidate.parts:
        raise ExternalEvidenceError(f"{label} must be a relative path")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ExternalEvidenceError(f"{label} contains an unsafe path component")
    return candidate.parts


def _read_regular(path: Path, *, max_bytes: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ExternalEvidenceError(f"{label} is unavailable: {exc}") from exc
    try:
        observed = os.fstat(descriptor)
        if not stat.S_ISREG(observed.st_mode):
            raise ExternalEvidenceError(f"{label} must be a regular file")
        if observed.st_size > max_bytes:
            raise ExternalEvidenceError(f"{label} exceeds the byte budget")
        chunks: list[bytes] = []
        remaining = observed.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ExternalEvidenceError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ExternalEvidenceError(f"{label} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _approved_root(value: Path) -> Path:
    expanded = value.expanduser()
    if expanded.is_symlink():
        raise ExternalEvidenceError("evidence root must not be a symlink")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise ExternalEvidenceError(f"evidence root is unavailable: {value}") from exc
    if not resolved.is_dir():
        raise ExternalEvidenceError("evidence root must be a directory")
    return resolved


def _resolve(root: Path, value: Any, label: str) -> Path:
    parts = _relative_parts(value, label)
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ExternalEvidenceError(f"{label} contains a symlink")
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise ExternalEvidenceError(f"{label} is unavailable") from exc
    if root != resolved and root not in resolved.parents:
        raise ExternalEvidenceError(f"{label} escapes the evidence root")
    if not resolved.is_file():
        raise ExternalEvidenceError(f"{label} must resolve to a regular file")
    return resolved


def _content_reference(value: Any, root: Path, label: str) -> tuple[dict[str, Any], bytes]:
    reference = _object(value, label)
    _exact_fields(reference, {"path", "sha256", "size_bytes", "media_type"}, label)
    _digest(reference["sha256"], f"{label}.sha256")
    size = _positive_int(reference["size_bytes"], f"{label}.size_bytes")
    media_type = _text(reference["media_type"], f"{label}.media_type")
    path = _resolve(root, reference["path"], f"{label}.path")
    raw = _read_regular(path, max_bytes=MAX_EVIDENCE_BYTES, label=label)
    observed = "sha256:" + hashlib.sha256(raw).hexdigest()
    if observed != reference["sha256"] or len(raw) != size:
        raise ExternalEvidenceError(f"{label} content digest or size does not match")
    return {
        "path": "/".join(_relative_parts(reference["path"], f"{label}.path")),
        "sha256": observed,
        "size_bytes": len(raw),
        "media_type": media_type,
    }, raw


def _decode_signature(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise ExternalEvidenceError("signed attestation signature is required")
    normalized = value.replace("-", "+").replace("_", "/")
    padded = normalized + "=" * (-len(normalized) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ExternalEvidenceError("signed attestation signature is not base64") from exc


def _parse_instant(value: Any, label: str) -> datetime:
    observed = _text(value, label)
    try:
        parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExternalEvidenceError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ExternalEvidenceError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class _TrustedKey:
    key_id: str
    actor_id: str
    organization_id: str
    role: str
    public_key: bytes
    public_key_digest: str
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True, slots=True)
class _TrustedStore:
    keys: Mapping[str, _TrustedKey]
    revoked_record_ids: frozenset[str]
    digest: str

    def verify_envelope(
        self,
        envelope: Mapping[str, Any],
        *,
        required_role: str,
        bindings: Mapping[str, Any],
        now: datetime | None,
    ) -> dict[str, str]:
        key_id = envelope.get("key_id")
        payload = envelope.get("payload")
        if not isinstance(key_id, str) or key_id not in self.keys:
            raise ExternalEvidenceError("signed attestation key is unknown or revoked")
        if not isinstance(payload, dict):
            raise ExternalEvidenceError("signed attestation payload must be an object")
        key = self.keys[key_id]
        observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if observed_now < key.not_before or observed_now >= key.not_after:
            raise ExternalEvidenceError("signed attestation key is outside its validity window")
        issued_at = _parse_instant(payload.get("issued_at"), "attestation.issued_at")
        expires_at = _parse_instant(payload.get("expires_at"), "attestation.expires_at")
        if issued_at < key.not_before or issued_at >= key.not_after or expires_at > key.not_after:
            raise ExternalEvidenceError("signed attestation timestamps exceed key validity")
        if expires_at <= issued_at or observed_now < issued_at or observed_now >= expires_at:
            raise ExternalEvidenceError("signed attestation is outside its validity window")
        record_id = payload.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ExternalEvidenceError("signed attestation record_id is required")
        if record_id in self.revoked_record_ids:
            raise ExternalEvidenceError("signed attestation record is revoked")
        for field, expected in bindings.items():
            if payload.get(field) != expected:
                raise ExternalEvidenceError(f"signed attestation binding mismatch: {field}")
        signature = _decode_signature(envelope.get("signature"))
        with tempfile.TemporaryDirectory(prefix="legacy-web-signature-") as temporary:
            base = Path(temporary)
            payload_path = base / "payload.json"
            signature_path = base / "signature.bin"
            public_key_path = base / "public-key.pem"
            payload_path.write_bytes(canonical_bytes(payload))
            signature_path.write_bytes(signature)
            public_key_path.write_bytes(key.public_key)
            try:
                completed = subprocess.run(
                    [
                        "openssl",
                        "pkeyutl",
                        "-verify",
                        "-pubin",
                        "-inkey",
                        str(public_key_path),
                        "-rawin",
                        "-in",
                        str(payload_path),
                        "-sigfile",
                        str(signature_path),
                    ],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExternalEvidenceError("Ed25519 verifier execution failed") from exc
        if completed.returncode != 0:
            raise ExternalEvidenceError("signed attestation signature verification failed")
        return {
            "record_id": record_id,
            "key_id": key_id,
            "payload_digest": canonical_digest(payload),
        }


def _load_trust_store(path: Path) -> tuple[_TrustedStore, dict[str, dict[str, Any]]]:
    supplied = path.expanduser()
    if supplied.is_symlink():
        raise ExternalEvidenceError("trust store must not be a symlink")
    try:
        raw = _read_regular(supplied, max_bytes=MAX_JSON_BYTES, label="trust store")
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ExternalEvidenceError) as exc:
        raise ExternalEvidenceError(f"trust store is invalid: {exc}") from exc
    document = _object(document, "trust store")
    _exact_fields(document, {"schema_version", "namespace", "keys", "revoked_record_ids"}, "trust store")
    if document["schema_version"] != SCHEMA_VERSION or document["namespace"] != NAMESPACE:
        raise ExternalEvidenceError("trust store identity is invalid")
    records = document.get("keys")
    if not isinstance(records, list):
        raise ExternalEvidenceError("trust store keys must be an array")
    metadata: dict[str, dict[str, Any]] = {}
    trusted_keys: dict[str, _TrustedKey] = {}
    key_material_digests: dict[str, str] = {}
    try:
        base = supplied.parent.resolve(strict=True)
    except OSError as exc:
        raise ExternalEvidenceError("trust store parent directory is unavailable") from exc
    for index, record in enumerate(records):
        item = _object(record, f"trust store keys[{index}]")
        _exact_fields(
            item,
            {
                "key_id",
                "actor_id",
                "organization_id",
                "roles",
                "public_key_path",
                "not_before",
                "not_after",
                "revoked",
            },
            f"trust store keys[{index}]",
        )
        key_id = _identity(item["key_id"], f"trust store keys[{index}].key_id")
        if key_id in metadata:
            raise ExternalEvidenceError(f"trust store key is duplicated: {key_id}")
        roles = item["roles"]
        if (
            not isinstance(roles, list)
            or len(roles) != 1
            or not isinstance(roles[0], str)
            or roles[0] not in set(EVIDENCE_ROLES.values())
        ):
            raise ExternalEvidenceError(f"trust store key role is invalid: {key_id}")
        public_key_path = _resolve(base, item["public_key_path"], f"trust store keys[{index}].public_key_path")
        public_key = _read_regular(public_key_path, max_bytes=64 * 1024, label=f"trust store key {key_id}")
        public_key_digest = "sha256:" + hashlib.sha256(public_key).hexdigest()
        if public_key_digest in key_material_digests.values():
            raise ExternalEvidenceError("trust store keys must use distinct public-key material")
        not_before = _parse_instant(item["not_before"], f"trust store keys[{index}].not_before")
        not_after = _parse_instant(item["not_after"], f"trust store keys[{index}].not_after")
        if not_after <= not_before:
            raise ExternalEvidenceError(f"trust store key validity window is invalid: {key_id}")
        metadata[key_id] = {
            "actor_id": _identity(item["actor_id"], f"trust store keys[{index}].actor_id"),
            "organization_id": _identity(
                item["organization_id"], f"trust store keys[{index}].organization_id"
            ),
            "role": roles[0],
            "revoked": item["revoked"],
        }
        if not isinstance(item["revoked"], bool):
            raise ExternalEvidenceError(f"trust store key revoked flag is invalid: {key_id}")
        key_material_digests[key_id] = public_key_digest
        if not item["revoked"]:
            trusted_keys[key_id] = _TrustedKey(
                key_id=key_id,
                actor_id=metadata[key_id]["actor_id"],
                organization_id=metadata[key_id]["organization_id"],
                role=metadata[key_id]["role"],
                public_key=public_key,
                public_key_digest=public_key_digest,
                not_before=not_before,
                not_after=not_after,
            )
    revoked = document["revoked_record_ids"]
    if not isinstance(revoked, list) or any(
        not isinstance(item, str) or not item for item in revoked
    ):
        raise ExternalEvidenceError("trust store revoked_record_ids must be a string array")
    for index, record_id in enumerate(revoked):
        _identity(record_id, f"trust store revoked_record_ids[{index}]")
    store = _TrustedStore(
        keys=trusted_keys,
        revoked_record_ids=frozenset(revoked),
        digest=canonical_digest(
            {
                "trust_store": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "public_keys": dict(sorted(key_material_digests.items())),
            }
        ),
    )
    return store, metadata


def _validate_binding(value: Any) -> dict[str, Any]:
    binding = _object(value, "intake.binding")
    _exact_fields(
        binding,
        {
            "package",
            "package_version",
            "archive_digest",
            "source_snapshot_digest",
            "target_artifact_digest",
            "target_profile_digest",
            "policy_snapshot_digest",
        },
        "intake.binding",
    )
    _identity(binding["package"], "intake.binding.package")
    _identity(binding["package_version"], "intake.binding.package_version")
    if binding["package"] != PACKAGE_NAME or binding["package_version"] != PACKAGE_VERSION:
        raise ExternalEvidenceError("intake.binding package identity is not the installed package")
    if binding["archive_digest"] != "sha256:" + EXPECTED_ARCHIVE_SHA256:
        raise ExternalEvidenceError("intake.binding archive digest is not the pinned source package")
    for field in (
        "archive_digest",
        "source_snapshot_digest",
        "target_artifact_digest",
        "target_profile_digest",
        "policy_snapshot_digest",
    ):
        _digest(binding[field], f"intake.binding.{field}")
    return dict(binding)


def _validate_organizations(value: Any) -> dict[str, str]:
    organizations = _object(value, "intake.organizations")
    _exact_fields(organizations, {"producer", "customer", "rootless", "independent", "certification"}, "intake.organizations")
    result = {key: _identity(organizations[key], f"intake.organizations.{key}") for key in organizations}
    if len(set(result.values())) != len(result):
        raise ExternalEvidenceError("evidence organizations must be distinct")
    return result


def _verify_attestation(
    *,
    store: Any,
    trust_metadata: dict[str, dict[str, Any]],
    envelope: Any,
    evidence_type: str,
    content: dict[str, Any],
    intake_id: str,
    binding_digest: str,
    executor: dict[str, str],
    organizations: dict[str, str],
    now: datetime | None,
) -> dict[str, Any]:
    expected_role = EVIDENCE_ROLES[evidence_type]
    expected_org = organizations[ORGANIZATION_BINDINGS[evidence_type]]
    item = _object(envelope, f"evidence.{evidence_type}.attestation")
    _exact_fields(item, {"algorithm", "key_id", "payload", "signature"}, f"evidence.{evidence_type}.attestation")
    if item["algorithm"] != "ed25519":
        raise ExternalEvidenceError(f"evidence.{evidence_type} must use ed25519")
    # Decode before invoking the shared verifier so malformed base64 is always
    # reported as an intake error and never passed to a lower-level command.
    _decode_signature(item["signature"])
    key_id = _identity(item["key_id"], f"evidence.{evidence_type}.attestation.key_id")
    metadata = trust_metadata.get(key_id)
    if metadata is None or metadata["revoked"]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} signing key is unavailable")
    if metadata["role"] != expected_role or metadata["organization_id"] != expected_org:
        raise ExternalEvidenceError(f"evidence.{evidence_type} signing identity is not role-bound")
    payload = _object(item["payload"], f"evidence.{evidence_type}.attestation.payload")
    _exact_fields(
        payload,
        {
            "record_id",
            "issued_at",
            "expires_at",
            "actor_id",
            "organization_id",
            "role",
            "intake_id",
            "binding_digest",
            "evidence_type",
            "content_digest",
            "content_size_bytes",
            "executor_actor_id",
            "executor_organization_id",
            "outcome",
            "evidence_class",
            "synthetic",
            "unknowns",
            "not_run",
            "claims",
        },
        f"evidence.{evidence_type}.attestation.payload",
    )
    if payload["actor_id"] != metadata["actor_id"] or payload["organization_id"] != metadata["organization_id"]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} signed actor identity does not match trust store")
    if payload["role"] != expected_role or payload["evidence_type"] != evidence_type:
        raise ExternalEvidenceError(f"evidence.{evidence_type} role binding is invalid")
    if payload["intake_id"] != intake_id or payload["binding_digest"] != binding_digest:
        raise ExternalEvidenceError(f"evidence.{evidence_type} intake binding is invalid")
    if payload["content_digest"] != content["sha256"] or payload["content_size_bytes"] != content["size_bytes"]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} content binding is invalid")
    if payload["executor_actor_id"] != executor["actor_id"] or payload["executor_organization_id"] != executor["organization_id"]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} executor binding is invalid")
    expected_outcome = "CERTIFIED" if evidence_type == "external_certification" else "ACCEPTED" if evidence_type == "customer_acceptance" else "PASS"
    if payload["outcome"] != expected_outcome or payload["evidence_class"] != "EXTERNAL_NON_SYNTHETIC":
        raise ExternalEvidenceError(f"evidence.{evidence_type} outcome is not admissible")
    if payload["synthetic"] is not False or payload["unknowns"] != [] or payload["not_run"] != []:
        raise ExternalEvidenceError(f"evidence.{evidence_type} contains synthetic or incomplete claims")
    if payload["claims"] != CLAIMS[evidence_type]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} claims do not satisfy the exact gate contract")
    if executor["actor_id"] == metadata["actor_id"] or executor["organization_id"] == metadata["organization_id"]:
        raise ExternalEvidenceError(f"evidence.{evidence_type} executor and verifier must be separate")
    try:
        receipt = store.verify_envelope(
            item,
            required_role=expected_role,
            bindings={
                "record_id": payload["record_id"],
                "actor_id": metadata["actor_id"],
                "organization_id": metadata["organization_id"],
                "role": expected_role,
                "intake_id": intake_id,
                "binding_digest": binding_digest,
                "evidence_type": evidence_type,
                "content_digest": content["sha256"],
                "content_size_bytes": content["size_bytes"],
                "executor_actor_id": executor["actor_id"],
                "executor_organization_id": executor["organization_id"],
                "outcome": expected_outcome,
                "evidence_class": "EXTERNAL_NON_SYNTHETIC",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
                "claims": CLAIMS[evidence_type],
            },
            now=now,
        )
    except (OSError, ValueError) as exc:
        raise ExternalEvidenceError(f"evidence.{evidence_type} signature verification failed") from exc
    return {
        "evidence_type": evidence_type,
        "record_id": receipt["record_id"],
        "key_id": receipt["key_id"],
        "actor_id": metadata["actor_id"],
        "organization_id": metadata["organization_id"],
        "content_digest": content["sha256"],
        "content_size_bytes": content["size_bytes"],
        "signature_verified": True,
    }


def evaluate_external_intake(
    intake: Mapping[str, Any],
    *,
    expected_binding: Mapping[str, Any],
    evidence_root: Path,
    trust_store: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify one complete external evidence intake without mutating state."""

    item = _object(intake, "intake")
    _exact_fields(item, {"schema_version", "namespace", "intake_id", "organizations", "binding", "evidence", "evidence_executors"}, "intake")
    if item["schema_version"] != SCHEMA_VERSION or item["namespace"] != NAMESPACE:
        raise ExternalEvidenceError("intake identity is invalid")
    intake_id = _identity(item["intake_id"], "intake.intake_id")
    binding = _validate_binding(item["binding"])
    expected = _validate_binding(expected_binding)
    if binding != expected:
        raise ExternalEvidenceError("intake binding does not match the local exact tuple")
    binding_digest = canonical_digest(binding)
    organizations = _validate_organizations(item["organizations"])
    executors = _object(item["evidence_executors"], "intake.evidence_executors")
    _exact_fields(executors, set(EVIDENCE_TYPES), "intake.evidence_executors")
    executor_values: dict[str, dict[str, str]] = {}
    for evidence_type in EVIDENCE_TYPES:
        executor = _object(executors[evidence_type], f"intake.evidence_executors.{evidence_type}")
        _exact_fields(executor, {"actor_id", "organization_id"}, f"intake.evidence_executors.{evidence_type}")
        executor_values[evidence_type] = {
            "actor_id": _identity(executor["actor_id"], f"intake.evidence_executors.{evidence_type}.actor_id"),
            "organization_id": _identity(executor["organization_id"], f"intake.evidence_executors.{evidence_type}.organization_id"),
        }
    evidence = _object(item["evidence"], "intake.evidence")
    _exact_fields(evidence, set(EVIDENCE_TYPES), "intake.evidence")
    root = _approved_root(evidence_root)
    store, trust_metadata = _load_trust_store(trust_store)
    verified: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    key_ids: set[str] = set()
    actor_ids: set[str] = set()
    content_digests: set[str] = set()
    for evidence_type in EVIDENCE_TYPES:
        entry = _object(evidence[evidence_type], f"intake.evidence.{evidence_type}")
        _exact_fields(entry, {"content", "attestation"}, f"intake.evidence.{evidence_type}")
        content, _ = _content_reference(entry["content"], root, f"intake.evidence.{evidence_type}.content")
        if content["sha256"] in content_digests:
            raise ExternalEvidenceError("evidence roles must bind distinct content bytes")
        content_digests.add(content["sha256"])
        receipt = _verify_attestation(
            store=store,
            trust_metadata=trust_metadata,
            envelope=entry["attestation"],
            evidence_type=evidence_type,
            content=content,
            intake_id=intake_id,
            binding_digest=binding_digest,
            executor=executor_values[evidence_type],
            organizations=organizations,
            now=now,
        )
        if (
            receipt["record_id"] in record_ids
            or receipt["key_id"] in key_ids
            or receipt["actor_id"] in actor_ids
        ):
            raise ExternalEvidenceError("evidence attestations must use distinct records and keys")
        record_ids.add(receipt["record_id"])
        key_ids.add(receipt["key_id"])
        actor_ids.add(receipt["actor_id"])
        verified.append(receipt)
    return {
        "schema_version": SCHEMA_VERSION,
        "namespace": NAMESPACE,
        "intake_id": intake_id,
        "binding_digest": binding_digest,
        "trust_store_digest": store.digest,
        "evidence_status": "VERIFIED_EXTERNAL_INTAKE",
        "verified_evidence_types": list(EVIDENCE_TYPES),
        "verified_evidence": verified,
        "decision": "READY_FOR_EXTERNAL_GATE_REVIEW",
        "externalEvidence": "VERIFIED_EXTERNAL_INTAKE",
        # The verifier is intentionally not the certifier and cannot mutate
        # the local engine's certification state.
        "certification": "NOT_CERTIFIED",
        "certification_promoted": False,
        "pack_status_mutated": False,
    }


def not_run_external_status(reason: str = "No signed external intake was supplied.") -> dict[str, Any]:
    """Return the explicit state used before an external intake exists."""

    return {
        "evidence_status": "NOT_RUN",
        "decision": "BLOCKED_EXTERNAL_EVIDENCE_REQUIRED",
        "reason": reason,
        "required_evidence_types": list(EVIDENCE_TYPES),
        "externalEvidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "certification_promoted": False,
    }


def _load_json(path: Path, label: str) -> dict[str, Any]:
    raw = _read_regular(path, max_bytes=MAX_JSON_BYTES, label=label)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalEvidenceError(f"{label} must be bounded UTF-8 JSON") from exc
    return _object(value, label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-legacy-web external-preflight")
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--expected-binding", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--trust-store", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate_external_intake(
            _load_json(args.intake, "external intake"),
            expected_binding=_load_json(args.expected_binding, "expected binding"),
            evidence_root=args.evidence_root,
            trust_store=args.trust_store,
        )
    except (ExternalEvidenceError, OSError, ValueError) as exc:
        print(f"EXTERNAL INTAKE FAIL: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists() and args.output.is_symlink():
            print("EXTERNAL INTAKE FAIL: output must not be a symlink", file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
