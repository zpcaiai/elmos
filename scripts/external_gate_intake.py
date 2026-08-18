#!/usr/bin/env python3
"""Validate signed Batch 29/35 external-gate evidence without certifying it.

The repository gates deliberately stop at a local readiness decision.  This
tool is the narrow handoff boundary for evidence produced outside the
repository owner organization.  It verifies immutable bytes, Ed25519 roles,
actor/organization bindings, stage metrics, and the exact subject snapshot.
Acceptance means only that the evidence is fit for a repository gate to
evaluate; it never updates route/pack status and never emits CERTIFIED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (  # noqa: E402
    DIGEST_PATTERN,
    TrustStore,
    canonical_digest,
    resolve_uri,
    verify_content_reference,
)

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - exercised through subprocess
    jsonschema = None
    JSONSCHEMA_IMPORT_ERROR = str(exc)
else:
    JSONSCHEMA_IMPORT_ERROR = None


NAMESPACE = "elmos.external-gate-intake"
INTAKE_SCHEMA = ROOT / "schemas/external-gates/intake.schema.json"
TRUST_SCHEMA = ROOT / "schemas/external-gates/trust-store.schema.json"
SUBJECT_SNAPSHOT_SCHEMA = ROOT / "schemas/external-gates/subject-snapshot.schema.json"

MAX_SUBJECT_FILES = 20_000
MAX_SINGLE_SUBJECT_BYTES = 512 * 1024 * 1024
MAX_TOTAL_SUBJECT_BYTES = 4 * 1024 * 1024 * 1024
MAX_SUBJECT_SCAN_DEPTH = 64
MAX_SUBJECT_SCAN_ENTRIES = 40_000

STAGE_PROFILES: dict[int, dict[str, set[str]]] = {
    29: {
        "independent_holdout": {
            "corpus-manifest",
            "source-build-result",
            "target-build-result",
            "behavior-comparison",
            "environment-manifest",
        },
        "representative_repository": {
            "repository-manifest",
            "source-build-result",
            "target-build-result",
            "behavior-comparison",
            "environment-manifest",
        },
        "external_execution": {
            "source-build-result",
            "target-build-result",
            "behavior-comparison",
            "environment-manifest",
        },
    },
    35: {
        "independent_holdout": {
            "corpus-manifest",
            "execution-result",
            "oracle-result",
            "environment-manifest",
        },
        "representative_production_workload": {
            "workload-manifest",
            "production-provenance",
            "data-authorization",
            "redaction-report",
            "execution-result",
            "oracle-result",
            "environment-manifest",
        },
    },
}

METRIC_PROFILES: dict[int, tuple[str, str, tuple[str, ...]]] = {
    29: (
        "tests_total",
        "tests_passed",
        (
            "tests_failed",
            "critical_unknowns",
            "critical_behavior_regressions",
            "test_integrity_violations",
        ),
    ),
    35: (
        "cases_total",
        "cases_passed",
        (
            "cases_failed",
            "p0_unknowns",
            "critical_failures",
            "test_integrity_violations",
        ),
    ),
}


class ExternalGateError(ValueError):
    """The intake cannot be accepted without fabricating or weakening evidence."""


def load_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ExternalGateError(f"non-finite JSON number is forbidden: {value}")

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalGateError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExternalGateError(f"JSON document must be an object: {path}")
    return payload


def validate_schema(document: dict[str, Any], schema_path: Path, label: str) -> None:
    if jsonschema is None:
        raise ExternalGateError(
            "jsonschema dependency is required for fail-closed validation: "
            f"{JSONSCHEMA_IMPORT_ERROR}"
        )
    try:
        jsonschema.validate(document, load_json(schema_path))
    except jsonschema.exceptions.ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ExternalGateError(
            f"{label} schema violation at {location}: {exc.message}"
        ) from exc
    except jsonschema.exceptions.SchemaError as exc:
        raise ExternalGateError(
            f"invalid repository schema {schema_path}: {exc.message}"
        ) from exc


def resolve_roots(values: list[Path]) -> tuple[Path, ...]:
    if not values:
        raise ExternalGateError("at least one --evidence-root is required")
    roots: list[Path] = []
    for value in values:
        resolved = value.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ExternalGateError(f"evidence root is not a directory: {resolved}")
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def trust_metadata(document: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        record["key_id"]: {
            "actor_id": record["actor_id"],
            "organization_id": record["organization_id"],
        }
        for record in document["keys"]
    }


def _read_path_snapshot(
    path: Path, *, max_bytes: int, label: str
) -> tuple[Path, bytes]:
    resolved = path.expanduser().resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(resolved, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ExternalGateError(f"{label} must be a regular file")
        if before.st_size > max_bytes:
            raise ExternalGateError(f"{label} exceeds the byte budget")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ExternalGateError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ExternalGateError(f"{label} changed while being read")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ExternalGateError(f"{label} changed while being read")
    finally:
        os.close(descriptor)
    current = os.stat(resolved, follow_symlinks=False)
    if not stat.S_ISREG(current.st_mode) or (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    ) != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ):
        raise ExternalGateError(f"{label} path changed while being read")
    return resolved, b"".join(chunks)


def read_verified_reference_bytes(
    reference: dict[str, Any],
    roots: tuple[Path, ...],
    *,
    max_bytes: int,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(reference, dict):
        raise ExternalGateError(f"{label} reference must be an object")
    expected_digest = reference.get("digest")
    if (
        not isinstance(expected_digest, str)
        or DIGEST_PATTERN.fullmatch(expected_digest) is None
    ):
        raise ExternalGateError(f"{label} digest must be exact SHA-256")
    expected_size = reference.get("size_bytes")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size < 0
    ):
        raise ExternalGateError(f"{label} size_bytes must be a non-negative integer")
    path = resolve_uri(reference.get("uri"), roots)
    resolved, content = _read_path_snapshot(path, max_bytes=max_bytes, label=label)
    observed_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if len(content) != expected_size:
        raise ExternalGateError(
            f"{label} byte count mismatch: expected {expected_size}, observed {len(content)}"
        )
    if observed_digest != expected_digest:
        raise ExternalGateError(
            f"{label} digest mismatch: expected {expected_digest}, observed {observed_digest}"
        )
    return (
        {
            "uri": reference["uri"],
            "digest": observed_digest,
            "size_bytes": len(content),
            "media_type": reference.get("media_type", "application/octet-stream"),
            "resolved_path": str(resolved),
        },
        content,
    )


def decode_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ExternalGateError(f"{label} contains non-finite JSON: {value}")

    try:
        document = json.loads(content.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ExternalGateError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ExternalGateError(f"{label} must be a JSON object")
    return document


def validate_subject_snapshot(
    snapshot_bytes: bytes, subject: dict[str, Any]
) -> dict[str, Any]:
    document = decode_json_bytes(snapshot_bytes, "external subject snapshot")
    validate_schema(document, SUBJECT_SNAPSHOT_SCHEMA, "external subject snapshot")
    expected = {
        "kind": subject["kind"],
        "key": subject["key"],
        "version": subject["version"],
    }
    for field, value in expected.items():
        if document.get(field) != value:
            raise ExternalGateError(f"subject snapshot {field} does not match intake")
    paths = [item["path"] for item in document["files"]]
    if len(paths) > MAX_SUBJECT_FILES:
        raise ExternalGateError(
            f"subject snapshot exceeds MAX_SUBJECT_FILES={MAX_SUBJECT_FILES}"
        )
    if len(paths) != len(set(paths)):
        raise ExternalGateError("subject snapshot contains duplicate file paths")
    total_bytes = 0
    for item in document["files"]:
        relative = item["path"]
        path_value = Path(relative)
        if path_value.is_absolute() or ".." in path_value.parts:
            raise ExternalGateError(f"subject snapshot file path is unsafe: {relative}")
        if len(path_value.parts) - 1 > MAX_SUBJECT_SCAN_DEPTH:
            raise ExternalGateError(
                f"subject snapshot file path exceeds MAX_SUBJECT_SCAN_DEPTH="
                f"{MAX_SUBJECT_SCAN_DEPTH}: {relative}"
            )
        byte_size = item["byte_size"]
        if byte_size > MAX_SINGLE_SUBJECT_BYTES:
            raise ExternalGateError(
                f"subject file {relative} exceeds MAX_SINGLE_SUBJECT_BYTES="
                f"{MAX_SINGLE_SUBJECT_BYTES}"
            )
        total_bytes += byte_size
        if total_bytes > MAX_TOTAL_SUBJECT_BYTES:
            raise ExternalGateError(
                f"subject snapshot exceeds MAX_TOTAL_SUBJECT_BYTES="
                f"{MAX_TOTAL_SUBJECT_BYTES}"
            )
    return document


def resolve_subject_root(value: Path) -> Path:
    supplied = value.expanduser()
    observed = os.stat(supplied, follow_symlinks=False)
    if not stat.S_ISDIR(observed.st_mode):
        raise ExternalGateError("subject root must be a real directory, not a symlink")
    return supplied.resolve(strict=True)


def _subject_root_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    entry_count = 0
    total_bytes = 0

    def visit(directory: Path, depth: int) -> None:
        nonlocal entry_count, total_bytes
        if depth > MAX_SUBJECT_SCAN_DEPTH:
            raise ExternalGateError(
                f"subject root exceeds MAX_SUBJECT_SCAN_DEPTH={MAX_SUBJECT_SCAN_DEPTH}"
            )
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_count += 1
                if entry_count > MAX_SUBJECT_SCAN_ENTRIES:
                    raise ExternalGateError(
                        "subject root exceeds MAX_SUBJECT_SCAN_ENTRIES="
                        f"{MAX_SUBJECT_SCAN_ENTRIES}"
                    )
                path = Path(entry.path)
                if entry.is_symlink():
                    raise ExternalGateError(
                        f"subject root contains a symlink: {path.relative_to(root)}"
                    )
                if entry.is_dir(follow_symlinks=False):
                    visit(path, depth + 1)
                elif entry.is_file(follow_symlinks=False):
                    relative = path.relative_to(root).as_posix()
                    files[relative] = path
                    if len(files) > MAX_SUBJECT_FILES:
                        raise ExternalGateError(
                            f"subject root exceeds MAX_SUBJECT_FILES={MAX_SUBJECT_FILES}"
                        )
                    observed_size = entry.stat(follow_symlinks=False).st_size
                    if observed_size > MAX_SINGLE_SUBJECT_BYTES:
                        raise ExternalGateError(
                            f"subject file {relative} exceeds "
                            f"MAX_SINGLE_SUBJECT_BYTES={MAX_SINGLE_SUBJECT_BYTES}"
                        )
                    total_bytes += observed_size
                    if total_bytes > MAX_TOTAL_SUBJECT_BYTES:
                        raise ExternalGateError(
                            "subject root exceeds MAX_TOTAL_SUBJECT_BYTES="
                            f"{MAX_TOTAL_SUBJECT_BYTES}"
                        )
                else:
                    raise ExternalGateError(
                        f"subject root contains a non-regular entry: {path.relative_to(root)}"
                    )

    visit(root, 0)
    return files


def _subject_identity(observed: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _stream_subject_digest(
    path: Path, *, expected_size: int, label: str
) -> tuple[str, tuple[int, int, int, int, int]]:
    path_before = os.stat(path, follow_symlinks=False)
    if not stat.S_ISREG(path_before.st_mode):
        raise ExternalGateError(f"{label} must be a regular file")
    if path_before.st_size != expected_size:
        raise ExternalGateError(
            f"{label} byte count mismatch: expected {expected_size}, "
            f"observed {path_before.st_size}"
        )
    if expected_size > MAX_SINGLE_SUBJECT_BYTES:
        raise ExternalGateError(
            f"{label} exceeds MAX_SINGLE_SUBJECT_BYTES={MAX_SINGLE_SUBJECT_BYTES}"
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or _subject_identity(
            before
        ) != _subject_identity(path_before):
            raise ExternalGateError(f"{label} changed before streaming verification")
        digest = hashlib.sha256()
        observed_size = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            observed_size += len(chunk)
            if observed_size > expected_size:
                raise ExternalGateError(
                    f"{label} byte count exceeds expected {expected_size}"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _subject_identity(after) != _subject_identity(before):
            raise ExternalGateError(f"{label} changed during streaming verification")
    finally:
        os.close(descriptor)
    if observed_size != expected_size:
        raise ExternalGateError(
            f"{label} byte count mismatch: expected {expected_size}, "
            f"observed {observed_size}"
        )
    path_after = os.stat(path, follow_symlinks=False)
    if _subject_identity(path_after) != _subject_identity(before):
        raise ExternalGateError(f"{label} changed during streaming verification")
    return "sha256:" + digest.hexdigest(), _subject_identity(before)


def verify_subject_files(
    document: dict[str, Any], subject_root: Path
) -> list[dict[str, Any]]:
    declared = {item["path"]: item for item in document["files"]}
    actual = _subject_root_files(subject_root)
    missing = sorted(set(declared) - set(actual))
    extra = sorted(set(actual) - set(declared))
    if missing:
        raise ExternalGateError(f"subject root is missing declared files: {missing}")
    if extra:
        raise ExternalGateError(
            f"subject root contains undeclared extra files: {extra}"
        )
    verified: list[dict[str, Any]] = []
    identities: dict[str, tuple[int, int, int, int, int]] = {}
    for relative in sorted(declared):
        item = declared[relative]
        supplied_path = actual[relative]
        resolved_path = supplied_path.resolve(strict=True)
        if subject_root != resolved_path and subject_root not in resolved_path.parents:
            raise ExternalGateError(f"subject file escapes subject root: {relative}")
        observed_digest, identities[relative] = _stream_subject_digest(
            resolved_path,
            expected_size=item["byte_size"],
            label=f"subject file {relative}",
        )
        if observed_digest != item["sha256"]:
            raise ExternalGateError(
                f"subject file {relative} digest mismatch: "
                f"expected {item['sha256']}, observed {observed_digest}"
            )
        verified.append(
            {
                "path": relative,
                "role": item["role"],
                "sha256": observed_digest,
                "byte_size": item["byte_size"],
            }
        )
    final = _subject_root_files(subject_root)
    if set(final) != set(actual):
        raise ExternalGateError("subject root file set changed during validation")
    for relative in sorted(declared):
        item = declared[relative]
        resolved_path = final[relative].resolve(strict=True)
        if subject_root != resolved_path and subject_root not in resolved_path.parents:
            raise ExternalGateError(f"subject file escapes subject root: {relative}")
        final_digest, final_identity = _stream_subject_digest(
            resolved_path,
            expected_size=item["byte_size"],
            label=f"subject file {relative} final verification",
        )
        if final_digest != item["sha256"]:
            raise ExternalGateError(
                f"subject file {relative} final digest mismatch: "
                f"expected {item['sha256']}, observed {final_digest}"
            )
        if final_identity != identities[relative]:
            raise ExternalGateError(
                f"subject file changed between verification passes: {relative}"
            )
    return verified


def validate_metrics(batch: int, stage: dict[str, Any]) -> None:
    metrics = stage["metrics"]
    total_name, passed_name, zero_names = METRIC_PROFILES[batch]
    total = metrics.get(total_name)
    passed = metrics.get(passed_name)
    if not isinstance(total, int) or isinstance(total, bool) or total < 1:
        raise ExternalGateError(
            f"{stage['stage']} {total_name} must be a positive integer"
        )
    if passed != total:
        raise ExternalGateError(
            f"{stage['stage']} {passed_name} must equal {total_name}"
        )
    for name in zero_names:
        if metrics.get(name) != 0:
            raise ExternalGateError(f"{stage['stage']} {name} must be explicitly zero")


def binding_digest(
    intake: dict[str, Any],
    stage: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> str:
    subject = intake["subject"]
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "intake_id": intake["intake_id"],
            "batch": intake["batch"],
            "subject": {
                "kind": subject["kind"],
                "key": subject["key"],
                "version": subject["version"],
                "producer": {
                    "actor_id": subject["producer"]["actor_id"],
                    "organization_id": subject["producer"]["organization_id"],
                },
                "snapshot_digest": subject["snapshot"]["digest"],
            },
            "stage": stage["stage"],
            "status": stage["status"],
            "metrics": stage["metrics"],
            "context": stage.get("context", {}),
            "evidence": [
                {
                    "role": item["role"],
                    "digest": item["artifact"]["digest"],
                    "size_bytes": item["artifact"]["size_bytes"],
                    "media_type": item["artifact"]["media_type"],
                }
                for item in sorted(evidence, key=lambda value: value["role"])
            ],
        }
    )


def verify_actor_envelope(
    *,
    envelope: dict[str, Any],
    role: str,
    expected: dict[str, Any],
    trust_store: TrustStore,
    metadata: dict[str, dict[str, str]],
    now: datetime | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    verification = trust_store.verify_envelope(
        envelope,
        required_role=role,
        bindings=expected,
        now=now,
    )
    key_metadata = metadata.get(envelope["key_id"])
    if key_metadata is None:
        raise ExternalGateError("signed envelope key metadata is missing")
    payload = envelope["payload"]
    for field in ("actor_id", "organization_id"):
        if payload.get(field) != key_metadata[field]:
            raise ExternalGateError(
                f"signed envelope {field} does not match trust-store identity"
            )
    return verification, key_metadata


def evaluate_intake(
    intake: dict[str, Any],
    *,
    trust_store_path: Path,
    expected_trust_store_digest: str,
    evidence_roots: tuple[Path, ...],
    subject_root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    validate_schema(intake, INTAKE_SCHEMA, "external intake")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", expected_trust_store_digest) is None:
        raise ExternalGateError(
            "pinned expected trust-store digest must be sha256:<64 lowercase hex>"
        )
    trust_store, trust_document = TrustStore.load_with_document(trust_store_path)
    validate_schema(trust_document, TRUST_SCHEMA, "external trust store")
    if trust_store.digest != expected_trust_store_digest:
        raise ExternalGateError(
            "trust-store composite digest does not match the repository-owner pin"
        )
    metadata = trust_metadata(trust_document)
    active_key_digests = [key.public_key_digest for key in trust_store.keys.values()]
    if len(active_key_digests) != len(set(active_key_digests)):
        raise ExternalGateError(
            "active trust-store roles must use distinct public keys"
        )
    subject = intake["subject"]
    producer_org = subject["producer"]["organization_id"]
    producer_actor = subject["producer"]["actor_id"]
    actor_organizations: dict[str, str] = {}
    for identity in metadata.values():
        previous = actor_organizations.setdefault(
            identity["actor_id"], identity["organization_id"]
        )
        if previous != identity["organization_id"]:
            raise ExternalGateError(
                "one trusted actor cannot claim multiple organizations"
            )
    producer_trusted_org = actor_organizations.setdefault(producer_actor, producer_org)
    if producer_trusted_org != producer_org:
        raise ExternalGateError(
            "producer actor organization conflicts with trusted actor identity"
        )

    batch = intake["batch"]
    profile = STAGE_PROFILES[batch]
    expected_kind = "batch29-route" if batch == 29 else "batch35-verification-pack"
    if subject["kind"] != expected_kind:
        raise ExternalGateError(f"Batch {batch} subject.kind must be {expected_kind}")

    snapshot, snapshot_bytes = read_verified_reference_bytes(
        subject["snapshot"],
        evidence_roots,
        max_bytes=4 * 1024 * 1024,
        label="subject snapshot",
    )
    snapshot_document = validate_subject_snapshot(snapshot_bytes, subject)
    verified_subject_files = verify_subject_files(
        snapshot_document, resolve_subject_root(subject_root)
    )
    stages = intake["stages"]
    by_name = {stage["stage"]: stage for stage in stages}
    if len(by_name) != len(stages) or set(by_name) != set(profile):
        raise ExternalGateError(
            f"Batch {batch} stages must be exactly {sorted(profile)}"
        )

    accepted_stages: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    for stage_name in sorted(profile):
        stage = by_name[stage_name]
        if stage["status"] != "PASSED":
            raise ExternalGateError(f"stage {stage_name} remains {stage['status']}")
        validate_metrics(batch, stage)

        evidence = stage["evidence"]
        evidence_by_role = {item["role"]: item for item in evidence}
        if (
            len(evidence_by_role) != len(evidence)
            or set(evidence_by_role) != profile[stage_name]
        ):
            raise ExternalGateError(
                f"{stage_name} evidence roles must be exactly {sorted(profile[stage_name])}"
            )
        verified_evidence = []
        evidence_digests: set[str] = set()
        for role in sorted(evidence_by_role):
            verified = verify_content_reference(
                evidence_by_role[role]["artifact"], evidence_roots
            )
            if verified["digest"] in evidence_digests:
                raise ExternalGateError(
                    f"{stage_name} cannot reuse one artifact for multiple evidence roles"
                )
            evidence_digests.add(verified["digest"])
            verified_evidence.append(
                {
                    key: value
                    for key, value in verified.items()
                    if key != "resolved_path"
                }
                | {"role": role}
            )

        if batch == 35 and stage_name == "representative_production_workload":
            context = stage.get("context", {})
            required_context = {
                "provenance": "production-derived",
                "authorized_use": "verification-only",
                "data_handling": "deidentified",
                "production_mutation": False,
            }
            for field, expected_value in required_context.items():
                if context.get(field) != expected_value:
                    raise ExternalGateError(
                        f"{stage_name} context {field} must be {expected_value!r}"
                    )

        stage_digest = binding_digest(intake, stage, evidence)
        bindings = {
            "namespace": NAMESPACE,
            "intake_id": intake["intake_id"],
            "batch": batch,
            "subject_digest": snapshot["digest"],
            "subject_key": subject["key"],
            "subject_version": subject["version"],
            "producer_actor_id": producer_actor,
            "producer_organization_id": producer_org,
            "stage": stage_name,
            "stage_binding_digest": stage_digest,
        }
        execution, executor = verify_actor_envelope(
            envelope=stage["execution"],
            role="external-executor",
            expected=bindings,
            trust_store=trust_store,
            metadata=metadata,
            now=now,
        )
        verification, verifier = verify_actor_envelope(
            envelope=stage["verification"],
            role="independent-verifier",
            expected=bindings,
            trust_store=trust_store,
            metadata=metadata,
            now=now,
        )
        if executor["actor_id"] == verifier["actor_id"]:
            raise ExternalGateError(
                f"{stage_name} executor and verifier actors must differ"
            )
        if producer_actor in {executor["actor_id"], verifier["actor_id"]}:
            raise ExternalGateError(
                f"{stage_name} producer actor cannot execute or independently verify"
            )
        if executor["organization_id"] == verifier["organization_id"]:
            raise ExternalGateError(
                f"{stage_name} executor and verifier organizations must differ"
            )
        if producer_org in {executor["organization_id"], verifier["organization_id"]}:
            raise ExternalGateError(
                f"{stage_name} producer organization cannot execute or independently verify"
            )

        envelope_results = [execution, verification]
        actors = [executor, verifier]
        if batch == 35 and stage_name == "representative_production_workload":
            if "authorization" not in stage:
                raise ExternalGateError(
                    "representative production authorization envelope is required"
                )
            authorization, authorizer = verify_actor_envelope(
                envelope=stage["authorization"],
                role="customer-workload-authorizer",
                expected=bindings,
                trust_store=trust_store,
                metadata=metadata,
                now=now,
            )
            if authorizer["actor_id"] == producer_actor:
                raise ExternalGateError(
                    "representative production producer actor cannot authorize workload use"
                )
            if authorizer["actor_id"] in {item["actor_id"] for item in actors}:
                raise ExternalGateError(
                    "representative production authorizer must differ from executor and verifier"
                )
            if authorizer["organization_id"] in {
                producer_org,
                executor["organization_id"],
                verifier["organization_id"],
            }:
                raise ExternalGateError(
                    "representative production authorizer organization must be independent"
                )
            envelope_results.append(authorization)

        for envelope_result in envelope_results:
            record_id = envelope_result["record_id"]
            if record_id in record_ids:
                raise ExternalGateError(
                    f"signed record is reused across stages: {record_id}"
                )
            record_ids.add(record_id)
        accepted_stages.append(
            {
                "stage": stage_name,
                "stage_binding_digest": stage_digest,
                "evidence": verified_evidence,
                "signed_records": envelope_results,
            }
        )

    return {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "intake_id": intake["intake_id"],
        "batch": batch,
        "subject": {
            "kind": subject["kind"],
            "key": subject["key"],
            "version": subject["version"],
            "snapshot_digest": snapshot["digest"],
            "repository_revision": snapshot_document["repository_revision"],
            "verified_file_count": len(verified_subject_files),
            "verified_files_digest": canonical_digest(verified_subject_files),
        },
        "decision": "ACCEPTED_FOR_REPOSITORY_GATE",
        "maximum_decision": "ACCEPTED_FOR_REPOSITORY_GATE",
        "certification_decision": "NOT_CERTIFIED",
        "external_evidence_only": True,
        "trust_store_digest": trust_store.digest,
        "accepted_stages": accepted_stages,
    }


def content_reference_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    resolved, content = _read_path_snapshot(
        path, max_bytes=4 * 1024 * 1024, label="subject snapshot"
    )
    return (
        {
            "uri": resolved.as_uri(),
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": "application/json",
        },
        content,
    )


def content_reference(path: Path) -> dict[str, Any]:
    reference, _content = content_reference_snapshot(path)
    return reference


def scaffold(args: argparse.Namespace) -> dict[str, Any]:
    batch = args.batch
    kind = "batch29-route" if batch == 29 else "batch35-verification-pack"
    stages = []
    for stage_name in sorted(STAGE_PROFILES[batch]):
        stage: dict[str, Any] = {
            "stage": stage_name,
            "status": "NOT_RUN",
            "metrics": {},
            "evidence": [],
        }
        if batch == 35 and stage_name == "representative_production_workload":
            stage["context"] = {
                "provenance": "NOT_RUN",
                "authorized_use": "NOT_RUN",
                "data_handling": "NOT_RUN",
                "production_mutation": False,
            }
        stages.append(stage)
    snapshot_reference, snapshot_bytes = content_reference_snapshot(
        args.subject_snapshot
    )
    result = {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "intake_id": args.intake_id,
        "batch": batch,
        "subject": {
            "kind": kind,
            "key": args.subject_key,
            "version": args.subject_version,
            "producer": {
                "actor_id": args.producer_actor,
                "organization_id": args.producer_organization,
            },
            "snapshot": snapshot_reference,
        },
        "stages": stages,
        "policy": {
            "repository_status_update": False,
            "production_operation_authorized": False,
            "maximum_local_decision": "ACCEPTED_FOR_REPOSITORY_GATE",
        },
    }
    snapshot_document = validate_subject_snapshot(snapshot_bytes, result["subject"])
    verify_subject_files(snapshot_document, resolve_subject_root(args.subject_root))
    return result


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    destination = path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="verify a signed external intake")
    validate.add_argument("--intake", type=Path, required=True)
    validate.add_argument("--trust-store", type=Path, required=True)
    validate.add_argument("--expected-trust-store-digest", required=True)
    validate.add_argument("--evidence-root", type=Path, action="append", required=True)
    validate.add_argument("--subject-root", type=Path, required=True)
    validate.add_argument("--output", type=Path)

    create = commands.add_parser("scaffold", help="create a fail-closed NOT_RUN intake")
    create.add_argument(
        "--batch", type=int, choices=sorted(STAGE_PROFILES), required=True
    )
    create.add_argument("--intake-id", required=True)
    create.add_argument("--subject-key", required=True)
    create.add_argument("--subject-version", required=True)
    create.add_argument("--subject-snapshot", type=Path, required=True)
    create.add_argument("--subject-root", type=Path, required=True)
    create.add_argument("--producer-actor", required=True)
    create.add_argument("--producer-organization", required=True)
    create.add_argument("--output", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "scaffold":
            result = scaffold(args)
            validate_schema(result, INTAKE_SCHEMA, "external intake scaffold")
            write_json_atomic(args.output, result)
            print(f"SCAFFOLDED_NOT_RUN: {args.output}")
            return 0
        intake = load_json(args.intake)
        result = evaluate_intake(
            intake,
            trust_store_path=args.trust_store,
            expected_trust_store_digest=args.expected_trust_store_digest,
            evidence_roots=resolve_roots(args.evidence_root),
            subject_root=args.subject_root,
        )
        if args.output is not None:
            write_json_atomic(args.output, result)
        print(
            f"EXTERNAL INTAKE PASS: batch={result['batch']} "
            f"subject={result['subject']['key']} decision={result['decision']} "
            "certification=NOT_CERTIFIED"
        )
        return 0
    except (ExternalGateError, OSError, ValueError) as exc:
        print(f"EXTERNAL INTAKE FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
