#!/usr/bin/env python3
"""Fail-closed Batch 29 gate for ten-language repository conversion evidence.

This gate evaluates local engineering evidence only.  A complete result can
prepare ``READY_FOR_EXTERNAL_GATE``; it can never certify a route, a language
pair, or the platform.  Every ordered pair and both bounded repository classes
must be present, and every referenced artifact is content verified below the
selected evidence root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN_SCHEMA = (
    ROOT / "schemas" / "batch29" / "repository-capability-campaign.schema.json"
)
RESULT_SCHEMA = ROOT / "schemas" / "batch29" / "repository-gate-result.schema.json"
GATE_IMPLEMENTATION = Path(__file__).resolve()

LANGUAGES = (
    "java",
    "python",
    "csharp",
    "typescript",
    "go",
    "rust",
    "cpp",
    "objc",
    "swift",
    "javascript",
)
EXPECTED_PAIRS = tuple(
    (source, target) for source in LANGUAGES for target in LANGUAGES if source != target
)
REPOSITORY_CLASSES = ("SMALL", "MEDIUM")
ROUTE_STATES = ("PASSED", "FAILED", "SKIPPED", "UNSUPPORTED", "NOT_RUN")

SMALL_MAX_FILES = 500
SMALL_MAX_BYTES = 8 * 1024 * 1024
MEDIUM_MAX_FILES = 5_000
MEDIUM_MAX_BYTES = 64 * 1024 * 1024

ARTIFACT_ROLES = {
    "SOURCE_REPOSITORY_SNAPSHOT",
    "SOURCE_BUILD_LOG",
    "SOURCE_TEST_LOG",
    "CLASSIFICATION_REPORT",
    "CONVERSION_REPORT",
    "TARGET_BUILD_LOG",
    "TARGET_TEST_LOG",
    "TARGET_REPOSITORY_ARTIFACT",
}
STAGES = {
    "inventory",
    "source_build",
    "source_test",
    "classification",
    "conversion",
    "target_build",
    "target_test",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass
class GateContext:
    evidence_root: Path | None
    failures: list[str] = field(default_factory=list)
    failure_set: set[str] = field(default_factory=set)
    executors: set[str] = field(default_factory=set)
    verifiers: set[str] = field(default_factory=set)
    artifact_ids: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_paths: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_inodes: dict[tuple[int, int], dict[str, Any]] = field(default_factory=dict)
    verified_files: dict[str, tuple[Path, str, int, int, int]] = field(
        default_factory=dict
    )
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    verified_artifact_references: int = 0

    def fail(self, message: str) -> None:
        if message not in self.failure_set:
            self.failure_set.add(message)
            self.failures.append(message)


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _is_integer(value: Any, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _exact_object(
    value: Any,
    expected_keys: set[str],
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        context.fail(f"{label} must be an object")
        return None
    missing = sorted(expected_keys - set(value))
    unexpected = sorted(set(value) - expected_keys)
    if missing:
        context.fail(f"{label} is missing fields: {', '.join(missing)}")
    if unexpected:
        context.fail(f"{label} has unexpected fields: {', '.join(unexpected)}")
    return value


def _safe_evidence_root(path: Path, context: GateContext) -> Path | None:
    try:
        if path.is_symlink() or not path.is_dir():
            raise ValueError("must be an existing non-symlink directory")
        return path.resolve(strict=True)
    except (OSError, ValueError) as exc:
        context.fail(f"evidence root is invalid: {exc}")
        return None


def _safe_artifact_path(
    relative: Any,
    label: str,
    context: GateContext,
) -> Path | None:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        context.fail(f"{label}.path must be a non-empty relative POSIX path")
        return None
    if "\\" in relative:
        context.fail(f"{label}.path must use POSIX separators")
        return None
    logical = PurePosixPath(relative)
    if logical.is_absolute() or any(part in {"", ".", ".."} for part in logical.parts):
        context.fail(f"{label}.path escapes or aliases the evidence root")
        return None
    if context.evidence_root is None:
        return None
    candidate = context.evidence_root.joinpath(*logical.parts)
    try:
        current = context.evidence_root
        for part in logical.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink components are forbidden")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(context.evidence_root):
            raise ValueError("resolved path leaves the evidence root")
        if not resolved.is_file():
            raise ValueError("artifact is not a regular file")
    except (OSError, ValueError) as exc:
        context.fail(f"{label}.path cannot be verified: {exc}")
        return None
    return resolved


def _verify_file(
    path: Path,
    expected_digest: str,
    expected_bytes: int,
    label: str,
    context: GateContext,
) -> tuple[bytes, int, int] | None:
    try:
        before = path.stat(follow_symlinks=False)
        content = path.read_bytes()
        after = path.stat(follow_symlinks=False)
    except OSError as exc:
        context.fail(f"{label} could not be read: {exc}")
        return None
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        context.fail(f"{label} changed while it was being verified")
        return None
    observed_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if len(content) != expected_bytes:
        context.fail(
            f"{label}.bytes mismatch: declared {expected_bytes}, observed {len(content)}"
        )
        return None
    if observed_digest != expected_digest:
        context.fail(f"{label}.sha256 mismatch")
        return None
    return content, after.st_dev, after.st_ino


def _expected_subject(
    subject_base: dict[str, str], stage: str, role: str
) -> dict[str, str]:
    return {**subject_base, "stage": stage, "role": role}


def _validate_subject(
    value: Any,
    expected: dict[str, str],
    label: str,
    context: GateContext,
) -> bool:
    subject = _exact_object(
        value,
        {
            "campaign_id",
            "route_id",
            "source_language",
            "target_language",
            "repository_id",
            "repository_class",
            "stage",
            "role",
        },
        label,
        context,
    )
    if subject is None:
        return False
    if subject != expected:
        context.fail(
            f"{label} does not match its campaign/route/repository/class/stage/role subject"
        )
        return False
    return True


def _validate_artifact(
    value: Any,
    expected_subject: dict[str, str],
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    artifact = _exact_object(
        value,
        {
            "artifact_id",
            "role",
            "subject",
            "path",
            "sha256",
            "bytes",
            "media_type",
        },
        label,
        context,
    )
    if artifact is None:
        return None

    artifact_id = artifact.get("artifact_id")
    role = artifact.get("role")
    subject = artifact.get("subject")
    relative = artifact.get("path")
    digest = artifact.get("sha256")
    byte_count = artifact.get("bytes")
    media_type = artifact.get("media_type")
    valid = True
    if not isinstance(artifact_id, str) or IDENTIFIER.fullmatch(artifact_id) is None:
        context.fail(f"{label}.artifact_id is invalid")
        valid = False
    expected_role = expected_subject["role"]
    if role not in ARTIFACT_ROLES or role != expected_role:
        context.fail(f"{label}.role must be {expected_role}")
        valid = False
    if not _validate_subject(subject, expected_subject, f"{label}.subject", context):
        valid = False
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        context.fail(f"{label}.sha256 must be a lowercase sha256 digest")
        valid = False
    if not _is_integer(byte_count, minimum=1):
        context.fail(f"{label}.bytes must be a positive integer")
        valid = False
    if media_type != "application/json":
        context.fail(f"{label}.media_type must be application/json")
        valid = False

    resolved = _safe_artifact_path(relative, label, context)
    if not valid or resolved is None:
        return None

    assert isinstance(artifact_id, str)
    assert isinstance(role, str)
    assert isinstance(relative, str)
    assert isinstance(digest, str)
    assert isinstance(byte_count, int)
    assert isinstance(media_type, str)
    if artifact_id in context.artifact_ids:
        context.fail(
            f"{label}.artifact_id is reused; every subject requires a unique artifact id"
        )
        return None
    if relative in context.artifact_paths:
        context.fail(
            f"{label}.path is reused; every subject requires a unique artifact path"
        )
        return None

    verified = _verify_file(resolved, digest, byte_count, label, context)
    if verified is None:
        return None
    content, device, inode = verified
    file_identity = (device, inode)
    if file_identity in context.artifact_inodes:
        context.fail(
            f"{label}.path is a hard-link reuse of another subject's evidence bytes"
        )
        return None
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        context.fail(f"{label} is not a UTF-8 JSON evidence document: {exc}")
        return None
    if not isinstance(document, dict):
        context.fail(f"{label} JSON evidence must be an object")
        return None

    binding = {
        "artifact_id": artifact_id,
        "role": role,
        "subject": expected_subject,
        "path": relative,
        "sha256": digest,
        "bytes": byte_count,
        "media_type": media_type,
    }
    context.artifact_ids[artifact_id] = binding
    context.artifact_paths[relative] = binding
    context.artifact_inodes[file_identity] = binding
    context.verified_files[relative] = (
        resolved,
        digest,
        byte_count,
        device,
        inode,
    )
    context.evidence_records.append(binding)
    context.verified_artifact_references += 1
    return {"reference": binding, "document": document}


def _validate_artifact_list(
    value: Any,
    expected_roles: tuple[str, ...],
    subject_base: dict[str, str],
    stage: str,
    label: str,
    context: GateContext,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        context.fail(f"{label} must be an array")
        return {}
    if len(value) != len(expected_roles):
        context.fail(
            f"{label} must contain exactly these roles: {', '.join(expected_roles)}"
        )
    observed_roles = [item.get("role") for item in value if isinstance(item, dict)]
    if Counter(observed_roles) != Counter(expected_roles):
        context.fail(f"{label} roles must be exactly: {', '.join(expected_roles)}")
    validated: dict[str, dict[str, Any]] = {}
    for index, actual in enumerate(value):
        actual_role = actual.get("role") if isinstance(actual, dict) else None
        if actual_role not in expected_roles:
            fallback = expected_roles[min(index, len(expected_roles) - 1)]
            expected = _expected_subject(subject_base, stage, fallback)
        else:
            expected = _expected_subject(subject_base, stage, str(actual_role))
        evidence = _validate_artifact(actual, expected, f"{label}[{index}]", context)
        if evidence is not None and actual_role in expected_roles:
            if actual_role in validated:
                context.fail(f"{label} repeats role {actual_role}")
            else:
                validated[str(actual_role)] = evidence
    return validated


def _validate_evidence_common(
    evidence: dict[str, Any],
    status: Any,
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    document = evidence["document"]
    reference = evidence["reference"]
    if document.get("schema_version") != "batch29.repository-evidence.v1":
        context.fail(f"{label}.schema_version is invalid")
    if document.get("subject") != reference["subject"]:
        context.fail(f"{label}.subject is not byte-bound to the artifact subject")
    if document.get("status") != status:
        context.fail(f"{label}.status differs from the campaign execution status")
    return document


def _validate_test_document(
    evidence: dict[str, Any] | None,
    execution: dict[str, Any],
    label: str,
    context: GateContext,
) -> None:
    if evidence is None:
        return
    document = _validate_evidence_common(
        evidence, execution.get("status"), label, context
    )
    if document is None:
        return
    document = _exact_object(
        document,
        {"schema_version", "subject", "status", "command", "tests"},
        label,
        context,
    )
    if document is None:
        return
    if document.get("command") != execution.get("command"):
        context.fail(f"{label}.command differs from the campaign argv")
    tests = document.get("tests")
    if not isinstance(tests, list) or not tests:
        context.fail(f"{label}.tests must contain raw test results")
        return
    identifiers: set[str] = set()
    derived = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0, "NOT_RUN": 0}
    for index, value in enumerate(tests):
        item = _exact_object(
            value, {"id", "status"}, f"{label}.tests[{index}]", context
        )
        if item is None:
            continue
        identifier = item.get("id")
        item_status = item.get("status")
        if not isinstance(identifier, str) or IDENTIFIER.fullmatch(identifier) is None:
            context.fail(f"{label}.tests[{index}].id is invalid")
        elif identifier in identifiers:
            context.fail(f"{label}.tests[{index}].id is duplicated")
        else:
            identifiers.add(identifier)
        if item_status not in derived:
            context.fail(f"{label}.tests[{index}].status is invalid")
        else:
            derived[str(item_status)] += 1
    expected = {
        "tests_total": len(tests),
        "tests_passed": derived["PASSED"],
        "tests_failed": derived["FAILED"],
        "tests_skipped": derived["SKIPPED"] + derived["NOT_RUN"],
    }
    for field_name, observed in expected.items():
        if execution.get(field_name) != observed:
            context.fail(
                f"{label} raw test detail derives {field_name}={observed}, not {execution.get(field_name)}"
            )


def _validate_execution(
    value: Any,
    expected_roles: tuple[str, ...],
    subject_base: dict[str, str],
    stage: str,
    label: str,
    context: GateContext,
    *,
    test_execution: bool = False,
) -> dict[str, dict[str, Any]]:
    keys = {"status", "executor", "verifier", "command", "artifacts"}
    if test_execution:
        keys |= {"tests_total", "tests_passed", "tests_failed", "tests_skipped"}
    execution = _exact_object(value, keys, label, context)
    if execution is None:
        return {}
    status = execution.get("status")
    if status not in ROUTE_STATES:
        context.fail(f"{label}.status is invalid")
    elif status != "PASSED":
        context.fail(
            f"{label}.status is {status}; NOT_RUN, skipped, failed, and unsupported states never pass"
        )

    executor = execution.get("executor")
    verifier = execution.get("verifier")
    executor_valid = isinstance(executor, str) and ACTOR.fullmatch(executor) is not None
    verifier_valid = isinstance(verifier, str) and ACTOR.fullmatch(verifier) is not None
    if not executor_valid:
        context.fail(f"{label}.executor is invalid")
    if not verifier_valid:
        context.fail(f"{label}.verifier is invalid")
    if executor_valid:
        context.executors.add(str(executor))
    if verifier_valid:
        context.verifiers.add(str(verifier))
    if executor_valid and verifier_valid and executor == verifier:
        context.fail(f"{label} executor and verifier must be different actors")

    command = execution.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(item, str) or not item.strip() for item in command)
    ):
        context.fail(f"{label}.command must be a non-empty argv array")

    artifacts = _validate_artifact_list(
        execution.get("artifacts"),
        expected_roles,
        subject_base,
        stage,
        f"{label}.artifacts",
        context,
    )

    if test_execution:
        counts = {
            name: execution.get(name)
            for name in (
                "tests_total",
                "tests_passed",
                "tests_failed",
                "tests_skipped",
            )
        }
        if not _is_integer(counts["tests_total"], minimum=1):
            context.fail(f"{label}.tests_total must be a positive integer")
            return artifacts
        for name in ("tests_passed", "tests_failed", "tests_skipped"):
            if not _is_integer(counts[name]):
                context.fail(f"{label}.{name} must be a non-negative integer")
                return artifacts
        if counts["tests_passed"] != counts["tests_total"]:
            context.fail(f"{label} did not pass every test")
        if counts["tests_failed"] != 0:
            context.fail(f"{label}.tests_failed must be zero")
        if counts["tests_skipped"] != 0:
            context.fail(f"{label}.tests_skipped must be zero")
        role = expected_roles[0]
        _validate_test_document(
            artifacts.get(role), execution, f"{label}.artifacts[{role}]", context
        )
    return artifacts


def _counter(
    value: dict[str, Any],
    name: str,
    label: str,
    context: GateContext,
    *,
    minimum: int = 0,
) -> int | None:
    observed = value.get(name)
    if not _is_integer(observed, minimum=minimum):
        context.fail(f"{label}.{name} must be an integer >= {minimum}")
        return None
    return int(observed)


def _validate_inventory(
    value: Any,
    repository_class: str,
    subject_base: dict[str, str],
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    inventory = _exact_object(
        value,
        {
            "repository_class",
            "file_count",
            "source_file_count",
            "source_bytes",
            "snapshot",
        },
        label,
        context,
    )
    if inventory is None:
        return None
    if inventory.get("repository_class") != repository_class:
        context.fail(f"{label}.repository_class does not match its workload")
    file_count = _counter(inventory, "file_count", label, context, minimum=1)
    source_file_count = _counter(
        inventory, "source_file_count", label, context, minimum=1
    )
    source_bytes = _counter(inventory, "source_bytes", label, context, minimum=1)
    snapshot = _validate_artifact(
        inventory.get("snapshot"),
        _expected_subject(subject_base, "inventory", "SOURCE_REPOSITORY_SNAPSHOT"),
        f"{label}.snapshot",
        context,
    )
    if file_count is None or source_file_count is None or source_bytes is None:
        return None
    if file_count > MEDIUM_MAX_FILES:
        context.fail(f"{label}.file_count exceeds the medium repository limit")
    if source_file_count > file_count:
        context.fail(f"{label}.source_file_count exceeds file_count")
    elif source_file_count != file_count:
        context.fail(
            f"{label} contains code outside the declared source language; "
            "a directed whole-repository workload must be single-source-language"
        )
    if source_bytes > MEDIUM_MAX_BYTES:
        context.fail(f"{label}.source_bytes exceeds the medium repository limit")

    source_paths: list[str] = []
    if snapshot is not None:
        document = _validate_evidence_common(
            snapshot, "PASSED", f"{label}.snapshot.document", context
        )
        if document is not None:
            document = _exact_object(
                document,
                {"schema_version", "subject", "status", "files"},
                f"{label}.snapshot.document",
                context,
            )
        files = document.get("files") if document is not None else None
        if not isinstance(files, list) or not files:
            context.fail(f"{label}.snapshot.document.files must be a non-empty array")
        else:
            seen_paths: set[str] = set()
            derived_source_bytes = 0
            derived_source_files = 0
            for index, raw_file in enumerate(files):
                item = _exact_object(
                    raw_file,
                    {"path", "language", "sha256", "bytes"},
                    f"{label}.snapshot.document.files[{index}]",
                    context,
                )
                if item is None:
                    continue
                path = item.get("path")
                language = item.get("language")
                item_digest = item.get("sha256")
                item_bytes = item.get("bytes")
                if not isinstance(path, str) or not path or "\\" in path:
                    context.fail(
                        f"{label}.snapshot.document.files[{index}].path is invalid"
                    )
                else:
                    logical = PurePosixPath(path)
                    if logical.is_absolute() or any(
                        part in {"", ".", ".."} for part in logical.parts
                    ):
                        context.fail(
                            f"{label}.snapshot.document.files[{index}].path is unsafe"
                        )
                    elif path in seen_paths:
                        context.fail(
                            f"{label}.snapshot.document.files[{index}].path is duplicated"
                        )
                    else:
                        seen_paths.add(path)
                        source_paths.append(path)
                if language != subject_base["source_language"]:
                    context.fail(
                        f"{label}.snapshot.document.files[{index}].language is not the route source"
                    )
                else:
                    derived_source_files += 1
                if (
                    not isinstance(item_digest, str)
                    or DIGEST.fullmatch(item_digest) is None
                ):
                    context.fail(
                        f"{label}.snapshot.document.files[{index}].sha256 is invalid"
                    )
                if not _is_integer(item_bytes, minimum=1):
                    context.fail(
                        f"{label}.snapshot.document.files[{index}].bytes is invalid"
                    )
                else:
                    derived_source_bytes += int(item_bytes)
            if file_count != len(files):
                context.fail(
                    f"{label}.file_count is {file_count}, raw inventory derives {len(files)}"
                )
            if source_file_count != derived_source_files:
                context.fail(
                    f"{label}.source_file_count is {source_file_count}, raw inventory derives {derived_source_files}"
                )
            if source_bytes != derived_source_bytes:
                context.fail(
                    f"{label}.source_bytes is {source_bytes}, raw inventory derives {derived_source_bytes}"
                )
    expected_class = (
        "SMALL"
        if file_count <= SMALL_MAX_FILES and source_bytes <= SMALL_MAX_BYTES
        else "MEDIUM"
    )
    if repository_class != expected_class:
        context.fail(
            f"{label} is classified {repository_class}, but its measured inventory is {expected_class}"
        )
    return {
        "file_count": file_count,
        "source_file_count": source_file_count,
        "source_bytes": source_bytes,
        "source_paths": source_paths,
    }


def _validate_classification(
    value: Any,
    subject_base: dict[str, str],
    source_paths: list[str],
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    classification = _exact_object(
        value,
        {
            "status",
            "total_units",
            "classified_units",
            "ready_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
            "unknown_units",
            "execution",
        },
        label,
        context,
    )
    if classification is None:
        return None
    status = classification.get("status")
    if status != "PASSED":
        context.fail(f"{label}.status must be PASSED, observed {status}")
    counts = {
        name: _counter(
            classification,
            name,
            label,
            context,
            minimum=1 if name == "total_units" else 0,
        )
        for name in (
            "total_units",
            "classified_units",
            "ready_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
            "unknown_units",
        )
    }
    artifacts = _validate_execution(
        classification.get("execution"),
        ("CLASSIFICATION_REPORT",),
        subject_base,
        "classification",
        f"{label}.execution",
        context,
    )
    if any(observed is None for observed in counts.values()):
        return None
    total = int(counts["total_units"])
    evidence = artifacts.get("CLASSIFICATION_REPORT")
    derived = {
        "total_units": 0,
        "classified_units": 0,
        "ready_units": 0,
        "unsupported_units": 0,
        "skipped_units": 0,
        "failed_units": 0,
        "unknown_units": 0,
    }
    unit_ids: set[str] = set()
    observed_source_paths: set[str] = set()
    verdict_fields = {
        "READY": "ready_units",
        "UNSUPPORTED": "unsupported_units",
        "SKIPPED": "skipped_units",
        "FAILED": "failed_units",
        "UNKNOWN": "unknown_units",
    }
    if evidence is not None:
        execution_value = classification.get("execution")
        execution_status = (
            execution_value.get("status") if isinstance(execution_value, dict) else None
        )
        document = _validate_evidence_common(
            evidence,
            execution_status,
            f"{label}.evidence",
            context,
        )
        if document is not None:
            document = _exact_object(
                document,
                {"schema_version", "subject", "status", "units"},
                f"{label}.evidence",
                context,
            )
        units = document.get("units") if document is not None else None
        if not isinstance(units, list) or not units:
            context.fail(f"{label}.evidence.units must contain raw classifications")
        else:
            derived["total_units"] = len(units)
            derived["classified_units"] = len(units)
            for index, raw_unit in enumerate(units):
                item = _exact_object(
                    raw_unit,
                    {"id", "source_path", "verdict"},
                    f"{label}.evidence.units[{index}]",
                    context,
                )
                if item is None:
                    continue
                identifier = item.get("id")
                source_path = item.get("source_path")
                verdict = item.get("verdict")
                if (
                    not isinstance(identifier, str)
                    or IDENTIFIER.fullmatch(identifier) is None
                ):
                    context.fail(f"{label}.evidence.units[{index}].id is invalid")
                elif identifier in unit_ids:
                    context.fail(f"{label}.evidence.units[{index}].id is duplicated")
                else:
                    unit_ids.add(identifier)
                if source_path not in source_paths:
                    context.fail(
                        f"{label}.evidence.units[{index}].source_path is not in the raw inventory"
                    )
                else:
                    observed_source_paths.add(str(source_path))
                field_name = verdict_fields.get(str(verdict))
                if field_name is None:
                    context.fail(f"{label}.evidence.units[{index}].verdict is invalid")
                else:
                    derived[field_name] += 1
            missing_source_paths = sorted(set(source_paths) - observed_source_paths)
            if missing_source_paths:
                context.fail(
                    f"{label}.evidence does not classify source files: "
                    + ", ".join(missing_source_paths[:10])
                )
    for field_name, observed in derived.items():
        if counts[field_name] != observed:
            context.fail(
                f"{label}.{field_name} is {counts[field_name]}, raw evidence derives {observed}"
            )
    if counts["classified_units"] != total:
        context.fail(f"{label} does not classify every unit")
    if counts["ready_units"] != total:
        context.fail(f"{label} does not mark every unit ready")
    for name in (
        "unsupported_units",
        "skipped_units",
        "failed_units",
        "unknown_units",
    ):
        if counts[name] != 0:
            context.fail(f"{label}.{name} must be zero")
    verdict_total = sum(
        int(counts[name])
        for name in (
            "ready_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
            "unknown_units",
        )
    )
    if verdict_total != total:
        context.fail(f"{label} verdict counts do not sum to total_units")
    return {"total_units": total, "unit_ids": unit_ids}


def _validate_conversion(
    value: Any,
    classified: dict[str, Any] | None,
    subject_base: dict[str, str],
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    conversion = _exact_object(
        value,
        {
            "status",
            "total_units",
            "attempted_units",
            "converted_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
            "execution",
        },
        label,
        context,
    )
    if conversion is None:
        return None
    status = conversion.get("status")
    if status != "PASSED":
        context.fail(f"{label}.status must be PASSED, observed {status}")
    counts = {
        name: _counter(
            conversion,
            name,
            label,
            context,
            minimum=1 if name == "total_units" else 0,
        )
        for name in (
            "total_units",
            "attempted_units",
            "converted_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
        )
    }
    artifacts = _validate_execution(
        conversion.get("execution"),
        ("CONVERSION_REPORT",),
        subject_base,
        "conversion",
        f"{label}.execution",
        context,
    )
    if any(observed is None for observed in counts.values()):
        return None
    total = int(counts["total_units"])
    if classified is not None and total != classified["total_units"]:
        context.fail(f"{label}.total_units differs from classification total")
    evidence = artifacts.get("CONVERSION_REPORT")
    derived = {
        "total_units": 0,
        "attempted_units": 0,
        "converted_units": 0,
        "unsupported_units": 0,
        "skipped_units": 0,
        "failed_units": 0,
    }
    unit_ids: set[str] = set()
    target_paths: set[str] = set()
    status_fields = {
        "CONVERTED": "converted_units",
        "UNSUPPORTED": "unsupported_units",
        "SKIPPED": "skipped_units",
        "FAILED": "failed_units",
        "NOT_RUN": None,
    }
    if evidence is not None:
        execution_value = conversion.get("execution")
        execution_status = (
            execution_value.get("status") if isinstance(execution_value, dict) else None
        )
        document = _validate_evidence_common(
            evidence, execution_status, f"{label}.evidence", context
        )
        if document is not None:
            document = _exact_object(
                document,
                {"schema_version", "subject", "status", "units"},
                f"{label}.evidence",
                context,
            )
        units = document.get("units") if document is not None else None
        if not isinstance(units, list) or not units:
            context.fail(f"{label}.evidence.units must contain raw conversion results")
        else:
            derived["total_units"] = len(units)
            for index, raw_unit in enumerate(units):
                item = _exact_object(
                    raw_unit,
                    {"id", "status", "target_paths"},
                    f"{label}.evidence.units[{index}]",
                    context,
                )
                if item is None:
                    continue
                identifier = item.get("id")
                unit_status = item.get("status")
                raw_target_paths = item.get("target_paths")
                if (
                    not isinstance(identifier, str)
                    or IDENTIFIER.fullmatch(identifier) is None
                ):
                    context.fail(f"{label}.evidence.units[{index}].id is invalid")
                elif identifier in unit_ids:
                    context.fail(f"{label}.evidence.units[{index}].id is duplicated")
                else:
                    unit_ids.add(identifier)
                if unit_status not in status_fields:
                    context.fail(f"{label}.evidence.units[{index}].status is invalid")
                else:
                    field_name = status_fields[str(unit_status)]
                    if unit_status != "NOT_RUN":
                        derived["attempted_units"] += 1
                    if field_name is not None:
                        derived[field_name] += 1
                if not isinstance(raw_target_paths, list):
                    context.fail(
                        f"{label}.evidence.units[{index}].target_paths must be an array"
                    )
                    continue
                if unit_status == "CONVERTED" and not raw_target_paths:
                    context.fail(
                        f"{label}.evidence.units[{index}] converted without target paths"
                    )
                for path_index, path in enumerate(raw_target_paths):
                    if not isinstance(path, str) or not path or "\\" in path:
                        context.fail(
                            f"{label}.evidence.units[{index}].target_paths[{path_index}] is invalid"
                        )
                        continue
                    logical = PurePosixPath(path)
                    if logical.is_absolute() or any(
                        part in {"", ".", ".."} for part in logical.parts
                    ):
                        context.fail(
                            f"{label}.evidence.units[{index}].target_paths[{path_index}] is unsafe"
                        )
                    else:
                        target_paths.add(path)
            if classified is not None and unit_ids != classified["unit_ids"]:
                context.fail(
                    f"{label}.evidence unit ids differ from classification evidence"
                )
    for field_name, observed in derived.items():
        if counts[field_name] != observed:
            context.fail(
                f"{label}.{field_name} is {counts[field_name]}, raw evidence derives {observed}"
            )
    if counts["attempted_units"] != total:
        context.fail(f"{label} did not attempt every unit")
    if counts["converted_units"] != total:
        context.fail(f"{label} did not convert every unit")
    for name in ("unsupported_units", "skipped_units", "failed_units"):
        if counts[name] != 0:
            context.fail(f"{label}.{name} must be zero")
    outcome_total = sum(
        int(counts[name])
        for name in (
            "converted_units",
            "unsupported_units",
            "skipped_units",
            "failed_units",
        )
    )
    if outcome_total != total:
        context.fail(f"{label} outcome counts do not sum to total_units")
    return {
        "total_units": total,
        "unit_ids": unit_ids,
        "target_paths": target_paths,
    }


def _validate_toolchain(value: Any, label: str, context: GateContext) -> None:
    toolchain = _exact_object(value, {"name", "version", "digest"}, label, context)
    if toolchain is None:
        return
    for name in ("name", "version"):
        if not isinstance(toolchain.get(name), str) or not toolchain[name].strip():
            context.fail(f"{label}.{name} must be non-empty")
    digest = toolchain.get("digest")
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        context.fail(f"{label}.digest is invalid")


def _validate_source_build_document(
    evidence: dict[str, Any] | None,
    execution: Any,
    source_paths: list[str],
    label: str,
    context: GateContext,
) -> None:
    if evidence is None or not isinstance(execution, dict):
        return
    document = _validate_evidence_common(
        evidence, execution.get("status"), label, context
    )
    if document is None:
        return
    document = _exact_object(
        document,
        {
            "schema_version",
            "subject",
            "status",
            "command",
            "exit_code",
            "toolchain",
            "source_paths",
        },
        label,
        context,
    )
    if document is None:
        return
    if document.get("command") != execution.get("command"):
        context.fail(f"{label}.command differs from the campaign argv")
    if document.get("exit_code") != 0:
        context.fail(f"{label}.exit_code must be zero")
    _validate_toolchain(document.get("toolchain"), f"{label}.toolchain", context)
    raw_paths = document.get("source_paths")
    if not isinstance(raw_paths, list) or any(
        not isinstance(path, str) for path in raw_paths
    ):
        context.fail(f"{label}.source_paths must be an array of paths")
    elif len(raw_paths) != len(set(raw_paths)):
        context.fail(f"{label}.source_paths contains duplicates")
    elif set(raw_paths) != set(source_paths):
        context.fail(f"{label}.source_paths does not cover the raw inventory")


def _validate_target_documents(
    artifacts: dict[str, dict[str, Any]],
    execution: Any,
    conversion: dict[str, Any] | None,
    label: str,
    context: GateContext,
) -> dict[str, Any] | None:
    if not isinstance(execution, dict):
        return None
    artifact_evidence = artifacts.get("TARGET_REPOSITORY_ARTIFACT")
    build_evidence = artifacts.get("TARGET_BUILD_LOG")
    manifest_unit_ids: set[str] = set()
    manifest_paths: set[str] = set()
    if artifact_evidence is not None:
        document = _validate_evidence_common(
            artifact_evidence, execution.get("status"), f"{label}.artifact", context
        )
        if document is not None:
            document = _exact_object(
                document,
                {"schema_version", "subject", "status", "unit_ids", "files"},
                f"{label}.artifact",
                context,
            )
        raw_unit_ids = document.get("unit_ids") if document is not None else None
        if not isinstance(raw_unit_ids, list) or not raw_unit_ids:
            context.fail(f"{label}.artifact.unit_ids must be non-empty raw detail")
        else:
            for index, identifier in enumerate(raw_unit_ids):
                if (
                    not isinstance(identifier, str)
                    or IDENTIFIER.fullmatch(identifier) is None
                ):
                    context.fail(f"{label}.artifact.unit_ids[{index}] is invalid")
                elif identifier in manifest_unit_ids:
                    context.fail(f"{label}.artifact.unit_ids[{index}] is duplicated")
                else:
                    manifest_unit_ids.add(identifier)
        raw_files = document.get("files") if document is not None else None
        if not isinstance(raw_files, list) or not raw_files:
            context.fail(f"{label}.artifact.files must be non-empty raw detail")
        else:
            for index, raw_file in enumerate(raw_files):
                item = _exact_object(
                    raw_file,
                    {"path", "sha256", "bytes"},
                    f"{label}.artifact.files[{index}]",
                    context,
                )
                if item is None:
                    continue
                path = item.get("path")
                item_digest = item.get("sha256")
                item_bytes = item.get("bytes")
                if not isinstance(path, str) or not path or "\\" in path:
                    context.fail(f"{label}.artifact.files[{index}].path is invalid")
                else:
                    logical = PurePosixPath(path)
                    if logical.is_absolute() or any(
                        part in {"", ".", ".."} for part in logical.parts
                    ):
                        context.fail(f"{label}.artifact.files[{index}].path is unsafe")
                    elif path in manifest_paths:
                        context.fail(
                            f"{label}.artifact.files[{index}].path is duplicated"
                        )
                    else:
                        manifest_paths.add(path)
                if (
                    not isinstance(item_digest, str)
                    or DIGEST.fullmatch(item_digest) is None
                ):
                    context.fail(f"{label}.artifact.files[{index}].sha256 is invalid")
                if not _is_integer(item_bytes, minimum=1):
                    context.fail(f"{label}.artifact.files[{index}].bytes is invalid")
        if conversion is not None:
            if manifest_unit_ids != conversion["unit_ids"]:
                context.fail(f"{label}.artifact.unit_ids differ from conversion detail")
            if manifest_paths != conversion["target_paths"]:
                context.fail(
                    f"{label}.artifact.files differ from conversion target paths"
                )

    if build_evidence is not None:
        document = _validate_evidence_common(
            build_evidence, execution.get("status"), f"{label}.build", context
        )
        if document is not None:
            document = _exact_object(
                document,
                {
                    "schema_version",
                    "subject",
                    "status",
                    "command",
                    "exit_code",
                    "toolchain",
                    "built_unit_ids",
                    "repository_artifact_sha256",
                },
                f"{label}.build",
                context,
            )
        if document is not None:
            if document.get("command") != execution.get("command"):
                context.fail(f"{label}.build.command differs from the campaign argv")
            if document.get("exit_code") != 0:
                context.fail(f"{label}.build.exit_code must be zero")
            _validate_toolchain(
                document.get("toolchain"), f"{label}.build.toolchain", context
            )
            built_unit_ids = document.get("built_unit_ids")
            if not isinstance(built_unit_ids, list) or len(built_unit_ids) != len(
                set(built_unit_ids)
            ):
                context.fail(f"{label}.build.built_unit_ids is invalid")
            elif set(built_unit_ids) != manifest_unit_ids:
                context.fail(
                    f"{label}.build.built_unit_ids differ from target artifact detail"
                )
            artifact_digest = (
                artifact_evidence["reference"]["sha256"]
                if artifact_evidence is not None
                else None
            )
            if document.get("repository_artifact_sha256") != artifact_digest:
                context.fail(
                    f"{label}.build.repository_artifact_sha256 is not bound to target artifact bytes"
                )
    return {
        "unit_ids": manifest_unit_ids,
        "paths": manifest_paths,
    }


def _validate_workload(
    value: Any,
    expected_class: str,
    campaign_id: str,
    route_id: str,
    source_language: str,
    target_language: str,
    label: str,
    context: GateContext,
) -> None:
    workload = _exact_object(
        value,
        {
            "repository_class",
            "repository_id",
            "source_inventory",
            "source_baseline",
            "classification",
            "conversion",
            "target_repository",
        },
        label,
        context,
    )
    if workload is None:
        return
    repository_class = workload.get("repository_class")
    if repository_class != expected_class:
        context.fail(f"{label}.repository_class must be {expected_class}")
    repository_id = workload.get("repository_id")
    if (
        not isinstance(repository_id, str)
        or IDENTIFIER.fullmatch(repository_id) is None
    ):
        context.fail(f"{label}.repository_id is invalid")
    subject_base = {
        "campaign_id": campaign_id,
        "route_id": route_id,
        "source_language": source_language,
        "target_language": target_language,
        "repository_id": str(repository_id),
        "repository_class": expected_class,
    }
    inventory = _validate_inventory(
        workload.get("source_inventory"),
        expected_class,
        subject_base,
        f"{label}.source_inventory",
        context,
    )
    source_paths = inventory["source_paths"] if inventory is not None else []

    baseline = _exact_object(
        workload.get("source_baseline"),
        {"build", "test"},
        f"{label}.source_baseline",
        context,
    )
    if baseline is not None:
        source_build_artifacts = _validate_execution(
            baseline.get("build"),
            ("SOURCE_BUILD_LOG",),
            subject_base,
            "source_build",
            f"{label}.source_baseline.build",
            context,
        )
        _validate_source_build_document(
            source_build_artifacts.get("SOURCE_BUILD_LOG"),
            baseline.get("build"),
            source_paths,
            f"{label}.source_baseline.build.evidence",
            context,
        )
        _validate_execution(
            baseline.get("test"),
            ("SOURCE_TEST_LOG",),
            subject_base,
            "source_test",
            f"{label}.source_baseline.test",
            context,
            test_execution=True,
        )

    classification = _validate_classification(
        workload.get("classification"),
        subject_base,
        source_paths,
        f"{label}.classification",
        context,
    )
    if (
        inventory is not None
        and classification is not None
        and classification["total_units"] < inventory["source_file_count"]
    ):
        context.fail(f"{label}.classification.total_units must cover every source file")
    conversion = _validate_conversion(
        workload.get("conversion"),
        classification,
        subject_base,
        f"{label}.conversion",
        context,
    )

    target = _exact_object(
        workload.get("target_repository"),
        {"whole_repository", "included_units", "excluded_units", "build", "test"},
        f"{label}.target_repository",
        context,
    )
    if target is not None:
        if target.get("whole_repository") is not True:
            context.fail(f"{label}.target_repository.whole_repository must be true")
        included = _counter(
            target, "included_units", f"{label}.target_repository", context
        )
        excluded = _counter(
            target, "excluded_units", f"{label}.target_repository", context
        )
        if conversion is not None and included != conversion["total_units"]:
            context.fail(
                f"{label}.target_repository.included_units differs from converted detail"
            )
        if excluded != 0:
            context.fail(f"{label}.target_repository.excluded_units must be zero")
        target_build_artifacts = _validate_execution(
            target.get("build"),
            ("TARGET_BUILD_LOG", "TARGET_REPOSITORY_ARTIFACT"),
            subject_base,
            "target_build",
            f"{label}.target_repository.build",
            context,
        )
        target_detail = _validate_target_documents(
            target_build_artifacts,
            target.get("build"),
            conversion,
            f"{label}.target_repository",
            context,
        )
        if target_detail is not None and included != len(target_detail["unit_ids"]):
            context.fail(
                f"{label}.target_repository.included_units differs from target artifact raw unit ids"
            )
        _validate_execution(
            target.get("test"),
            ("TARGET_TEST_LOG",),
            subject_base,
            "target_test",
            f"{label}.target_repository.test",
            context,
            test_execution=True,
        )


def _validate_route(
    value: Any,
    index: int,
    campaign_id: str,
    context: GateContext,
    route_status_counts: dict[str, int],
    repository_class_counts: dict[str, int],
) -> tuple[tuple[str, str] | None, int]:
    label = f"routes[{index}]"
    route = _exact_object(
        value,
        {"route_id", "source_language", "target_language", "status", "workloads"},
        label,
        context,
    )
    if route is None:
        return None, 0
    source = route.get("source_language")
    target = route.get("target_language")
    route_id = route.get("route_id")
    pair: tuple[str, str] | None = None
    if source not in LANGUAGES:
        context.fail(f"{label}.source_language is invalid")
    if target not in LANGUAGES:
        context.fail(f"{label}.target_language is invalid")
    if source in LANGUAGES and target in LANGUAGES:
        if source == target:
            context.fail(f"{label} is self-directed")
        else:
            pair = (str(source), str(target))
            expected_route_id = f"{source}-to-{target}"
            if route_id != expected_route_id:
                context.fail(f"{label}.route_id must be {expected_route_id}")
    elif not isinstance(route_id, str):
        context.fail(f"{label}.route_id is invalid")

    status = route.get("status")
    if status in ROUTE_STATES:
        route_status_counts[str(status)] += 1
        if status != "PASSED":
            context.fail(
                f"{label}.status is {status}; every directed repository route must pass"
            )
    else:
        context.fail(f"{label}.status is invalid")

    workloads = route.get("workloads")
    if not isinstance(workloads, list):
        context.fail(f"{label}.workloads must be an array")
        return pair, 0
    observed_count = len(workloads)
    if observed_count != len(REPOSITORY_CLASSES):
        context.fail(f"{label}.workloads must contain exactly SMALL and MEDIUM")
    classes = [
        item.get("repository_class") for item in workloads if isinstance(item, dict)
    ]
    if Counter(classes) != Counter(REPOSITORY_CLASSES):
        context.fail(f"{label}.workloads must contain one SMALL and one MEDIUM")
    by_class = {
        item.get("repository_class"): item
        for item in workloads
        if isinstance(item, dict) and item.get("repository_class") in REPOSITORY_CLASSES
    }
    for repository_class in REPOSITORY_CLASSES:
        workload = by_class.get(repository_class)
        if workload is None:
            continue
        repository_class_counts[repository_class] += 1
        _validate_workload(
            workload,
            repository_class,
            campaign_id,
            str(route_id),
            str(source),
            str(target),
            f"{label}.workloads[{repository_class}]",
            context,
        )
    return pair, observed_count


def _validate_campaign_schema(campaign: Any, context: GateContext) -> None:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        context.fail(
            "jsonschema is required for the repository capability gate; schema validation was NOT_RUN"
        )
        return
    try:
        schema = json.loads(CAMPAIGN_SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        errors = sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(campaign),
            key=lambda error: [str(item) for item in error.absolute_path],
        )
    except Exception as exc:  # pragma: no cover - dependency-specific error shape
        context.fail(f"campaign schema could not be applied: {exc}")
        return
    if errors:
        first = errors[0]
        pointer = "/".join(str(item) for item in first.absolute_path)
        context.fail(f"campaign schema violation at /{pointer}: {first.message}")


def _final_reverify(context: GateContext) -> None:
    for relative, (
        path,
        digest,
        byte_count,
        expected_device,
        expected_inode,
    ) in sorted(context.verified_files.items()):
        verified = _verify_file(
            path,
            digest,
            byte_count,
            f"final artifact recheck {relative}",
            context,
        )
        if verified is not None and verified[1:] != (expected_device, expected_inode):
            context.fail(f"final artifact recheck {relative} changed file identity")


def _build_result(
    *,
    campaign_id: str | None,
    campaign_digest: str | None,
    context: GateContext,
    observed_route_count: int,
    observed_workload_count: int,
    route_status_counts: dict[str, int],
    repository_class_counts: dict[str, int],
) -> dict[str, Any]:
    actor_overlap = sorted(context.executors & context.verifiers)
    if actor_overlap:
        context.fail(
            "executor/verifier role sets overlap across the campaign: "
            + ", ".join(actor_overlap)
        )
    actor_separation = (
        bool(context.executors)
        and bool(context.verifiers)
        and not bool(context.executors & context.verifiers)
    )
    if not actor_separation:
        context.fail("campaign-wide executor/verifier separation was not demonstrated")
    _final_reverify(context)

    ready = not context.failures
    evidence_set_digest = _canonical_digest(
        sorted(context.evidence_records, key=lambda item: str(item["artifact_id"]))
    )
    result_without_digest = {
        "schema_version": "batch29.repository-gate-result.v1",
        "kind": "elmos.batch29.repository-gate-result",
        "campaign_id": campaign_id,
        "campaign_digest": campaign_digest,
        "campaign_schema_digest": _file_digest(CAMPAIGN_SCHEMA),
        "result_schema_digest": _file_digest(RESULT_SCHEMA),
        "gate_implementation_digest": _file_digest(GATE_IMPLEMENTATION),
        "evidence_set_digest": evidence_set_digest,
        "gate_status": "PASSED_LOCAL_ENGINEERING" if ready else "FAILED",
        "decision": "READY_FOR_EXTERNAL_GATE" if ready else "LIMITED",
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "certification_decision": "NOT_CERTIFIED",
        "external_verification_status": "NOT_RUN",
        "expected_route_count": len(EXPECTED_PAIRS),
        "observed_route_count": observed_route_count,
        "expected_workload_count": len(EXPECTED_PAIRS) * len(REPOSITORY_CLASSES),
        "observed_workload_count": observed_workload_count,
        "route_status_counts": route_status_counts,
        "repository_class_counts": repository_class_counts,
        "verified_artifact_reference_count": context.verified_artifact_references,
        "unique_verified_artifact_count": len(context.verified_files),
        "actor_separation_passed": actor_separation,
        "failures": context.failures,
    }
    return {
        **result_without_digest,
        "result_digest": _canonical_digest(result_without_digest),
    }


def evaluate_repository_gate(campaign: Any, evidence_root: Path) -> dict[str, Any]:
    """Evaluate one campaign without executing repository or provider commands."""

    context = GateContext(evidence_root=None)
    context.evidence_root = _safe_evidence_root(evidence_root, context)
    route_status_counts = {state: 0 for state in ROUTE_STATES}
    repository_class_counts = {name: 0 for name in REPOSITORY_CLASSES}
    observed_route_count = 0
    observed_workload_count = 0
    campaign_id: str | None = None
    try:
        campaign_digest = _canonical_digest(campaign)
    except (TypeError, ValueError):
        campaign_digest = None
        context.fail("campaign is not canonical JSON and cannot be digest-bound")

    _validate_campaign_schema(campaign, context)
    root = _exact_object(
        campaign,
        {
            "schema_version",
            "kind",
            "campaign_id",
            "languages",
            "scope",
            "routes",
            "external_verification_status",
            "certification_status",
        },
        "campaign",
        context,
    )
    if root is not None:
        if root.get("schema_version") != "batch29.repository-capability-campaign.v1":
            context.fail("campaign.schema_version is invalid")
        if root.get("kind") != "elmos.batch29.repository-capability-campaign":
            context.fail("campaign.kind is invalid")
        raw_campaign_id = root.get("campaign_id")
        if (
            not isinstance(raw_campaign_id, str)
            or IDENTIFIER.fullmatch(raw_campaign_id) is None
        ):
            context.fail("campaign.campaign_id is invalid")
        else:
            campaign_id = raw_campaign_id
        if root.get("languages") != list(LANGUAGES):
            context.fail(
                "campaign.languages must be the exact ordered ten-language set"
            )
        scope = _exact_object(
            root.get("scope"),
            {"profile", "repository_classes", "execution_boundary"},
            "campaign.scope",
            context,
        )
        if scope is not None:
            if scope.get("profile") != "repository-wide-v1":
                context.fail("campaign.scope.profile must be repository-wide-v1")
            if scope.get("repository_classes") != list(REPOSITORY_CLASSES):
                context.fail(
                    "campaign.scope.repository_classes must be exactly SMALL and MEDIUM"
                )
            if scope.get("execution_boundary") != "LOCAL_ENGINEERING":
                context.fail(
                    "campaign.scope.execution_boundary must be LOCAL_ENGINEERING"
                )
        if root.get("external_verification_status") != "NOT_RUN":
            context.fail(
                "campaign.external_verification_status must remain NOT_RUN at this local gate"
            )
        if root.get("certification_status") != "NOT_CERTIFIED":
            context.fail("campaign.certification_status must remain NOT_CERTIFIED")

        routes = root.get("routes")
        if not isinstance(routes, list):
            context.fail("campaign.routes must be an array")
        else:
            observed_route_count = len(routes)
            if observed_route_count != len(EXPECTED_PAIRS):
                context.fail(
                    f"campaign.routes must contain exactly {len(EXPECTED_PAIRS)} directed routes"
                )
            observed_pairs: list[tuple[str, str]] = []
            for index, route in enumerate(routes):
                pair, workload_count = _validate_route(
                    route,
                    index,
                    campaign_id or "invalid-campaign",
                    context,
                    route_status_counts,
                    repository_class_counts,
                )
                observed_workload_count += workload_count
                if pair is not None:
                    observed_pairs.append(pair)
            pair_counts = Counter(observed_pairs)
            duplicates = sorted(
                pair for pair, count in pair_counts.items() if count != 1
            )
            missing = sorted(set(EXPECTED_PAIRS) - set(observed_pairs))
            unexpected = sorted(set(observed_pairs) - set(EXPECTED_PAIRS))
            if duplicates:
                context.fail(
                    "campaign.routes contains duplicate directed pairs: "
                    + ", ".join(
                        f"{source}-to-{target}" for source, target in duplicates
                    )
                )
            if missing:
                context.fail(
                    "campaign.routes is missing directed pairs: "
                    + ", ".join(f"{source}-to-{target}" for source, target in missing)
                )
            if unexpected:
                context.fail(
                    "campaign.routes contains unexpected directed pairs: "
                    + ", ".join(
                        f"{source}-to-{target}" for source, target in unexpected
                    )
                )

    return _build_result(
        campaign_id=campaign_id,
        campaign_digest=campaign_digest,
        context=context,
        observed_route_count=observed_route_count,
        observed_workload_count=observed_workload_count,
        route_status_counts=route_status_counts,
        repository_class_counts=repository_class_counts,
    )


def _load_failure_result(message: str) -> dict[str, Any]:
    context = GateContext(evidence_root=None)
    context.fail(message)
    return _build_result(
        campaign_id=None,
        campaign_digest=None,
        context=context,
        observed_route_count=0,
        observed_workload_count=0,
        route_status_counts={state: 0 for state in ROUTE_STATES},
        repository_class_counts={name: 0 for name in REPOSITORY_CLASSES},
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the Batch 29 small/medium repository route matrix"
    )
    parser.add_argument("campaign", type=Path)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="Root for relative artifact paths (defaults to the campaign directory)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = _load_failure_result(f"campaign could not be loaded: {exc}")
    else:
        evidence_root = args.evidence_root or args.campaign.parent
        result = evaluate_repository_gate(campaign, evidence_root)

    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(
                f"repository gate output could not be written: {exc}", file=sys.stderr
            )
            return 2
    print(rendered, end="")
    return 0 if result["gate_status"] == "PASSED_LOCAL_ENGINEERING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
