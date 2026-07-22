#!/usr/bin/env python3
"""Shared fail-closed validation helpers for the Batch 1-37 strict suite."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
CASE_ID_RE = re.compile(r"^[A-Z0-9-]+$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]+$")
ZERO_DIGEST = "sha256:" + "0" * 64
STATUSES = {"passed", "failed", "blocked", "not-run", "waived"}
SEVERITIES = {"P0", "P1", "P2", "P3"}
TEST_TYPES = {
    "happy_path",
    "boundary",
    "negative",
    "dependency_failure",
    "security",
    "replay_idempotency",
    "version_drift",
    "evidence_tamper",
}
CASE_REQUIRED = {
    "id",
    "skill",
    "batches",
    "capability",
    "severity",
    "test_type",
    "title",
    "preconditions",
    "steps",
    "assertions",
    "evidence_required",
    "anti_cheat",
}
RESULT_REQUIRED = {
    "case_id",
    "status",
    "artifact_digest",
    "environment_digest",
    "started_at",
    "finished_at",
    "evidence",
}
MANIFEST_REQUIRED = {
    "manifest_version",
    "manifest_id",
    "case_id",
    "case_digest",
    "catalog_digest",
    "artifact_digest",
    "environment_digest",
    "execution_kind",
    "started_at",
    "finished_at",
    "executor",
    "verifier",
    "authorization_refs",
    "files",
    "corpora",
}


class ValidationError(ValueError):
    """Raised for malformed or unsafe suite inputs."""


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256(value).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def sha256_file(path: Path | str, *, prefixed: bool = False) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def sha256_json(value: Any, *, prefixed: bool = True) -> str:
    return sha256_bytes(canonical_bytes(value), prefixed=prefixed)


def resolve_beneath(base: Path, reference: str, *, must_exist: bool = True) -> Path:
    if not isinstance(reference, str) or not reference or "\x00" in reference:
        raise ValidationError("path reference must be a non-empty string")
    candidate = (base / reference).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ValidationError(f"path escapes allowed root: {reference}") from exc
    if must_exist and not candidate.is_file():
        raise ValidationError(f"file does not exist: {reference}")
    return candidate


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValidationError("timestamp is required")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"timestamp must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def require_digest(value: Any, label: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
        raise ValidationError(f"{label} must be a sha256 digest")
    if not allow_zero and value == ZERO_DIGEST:
        raise ValidationError(f"{label} cannot be the placeholder digest")
    return value


def require_string_list(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    unique: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValidationError(f"{label} must contain at least {minimum} item(s)")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{label} must contain non-empty strings")
    if unique and len(value) != len(set(value)):
        raise ValidationError(f"{label} must not contain duplicates")
    return value


def validate_case(case: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case must be an object"]
    missing = CASE_REQUIRED - set(case)
    if missing:
        errors.append(f"missing fields {sorted(missing)}")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        errors.append("invalid case id")
    skill = case.get("skill")
    if not isinstance(skill, str) or not SKILL_NAME_RE.fullmatch(skill):
        errors.append("invalid skill name")
    batches = case.get("batches")
    if (
        not isinstance(batches, list)
        or not batches
        or any(not isinstance(item, int) or isinstance(item, bool) or not 1 <= item <= 37 for item in batches)
        or len(batches) != len(set(batches))
    ):
        errors.append("batches must be unique integers from 1 through 37")
    if case.get("severity") not in SEVERITIES:
        errors.append("invalid severity")
    if case.get("test_type") not in TEST_TYPES:
        errors.append("invalid test_type")
    for field, minimum in (
        ("preconditions", 1),
        ("steps", 3),
        ("assertions", 3),
        ("evidence_required", 2),
        ("anti_cheat", 1),
    ):
        try:
            require_string_list(case.get(field), field, minimum=minimum, unique=True)
        except ValidationError as exc:
            errors.append(str(exc))
    timeout = case.get("timeout_seconds")
    if timeout is not None and (
        not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1
    ):
        errors.append("timeout_seconds must be a positive integer")
    retries = case.get("retries")
    if retries is not None and (
        not isinstance(retries, int)
        or isinstance(retries, bool)
        or retries < 0
        or retries > 2
    ):
        errors.append("retries must be an integer from 0 through 2")
    for field in ("holdout_required", "representative_workload_required"):
        if field in case and not isinstance(case[field], bool):
            errors.append(f"{field} must be boolean")
    return errors


def validate_result_shape(result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    missing = RESULT_REQUIRED - set(result)
    if missing:
        errors.append(f"missing result fields {sorted(missing)}")
    status = result.get("status")
    if status not in STATUSES:
        errors.append(f"invalid result status: {status}")
    allow_zero = status == "not-run"
    for field in ("artifact_digest", "environment_digest"):
        try:
            require_digest(result.get(field), field, allow_zero=allow_zero)
        except ValidationError as exc:
            errors.append(str(exc))
    evidence = result.get("evidence")
    if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
        errors.append("evidence must be an array of paths")
    if status == "not-run":
        if result.get("started_at") or result.get("finished_at") or evidence:
            errors.append("not-run results cannot contain timestamps or evidence")
    else:
        try:
            started = parse_utc(result.get("started_at"))
            finished = parse_utc(result.get("finished_at"))
            if finished < started:
                errors.append("finished_at precedes started_at")
        except ValidationError as exc:
            errors.append(str(exc))
    if status == "passed":
        if not evidence:
            errors.append("passed results require evidence")
        if not isinstance(result.get("replay_command"), str) or not result["replay_command"].strip():
            errors.append("passed results require replay_command")
        if result.get("execution_kind") not in {"real", "approved-equivalent"}:
            errors.append("passed results require real or approved-equivalent execution_kind")
    return errors


def validate_evidence_manifest_shape(manifest: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["evidence manifest must be an object"]
    missing = MANIFEST_REQUIRED - set(manifest)
    if missing:
        errors.append(f"missing evidence fields {sorted(missing)}")
    if manifest.get("manifest_version") != 2:
        errors.append("manifest_version must be 2")
    for field in ("case_digest", "catalog_digest", "artifact_digest", "environment_digest"):
        try:
            require_digest(manifest.get(field), field)
        except ValidationError as exc:
            errors.append(str(exc))
    if manifest.get("execution_kind") not in {"real", "approved-equivalent"}:
        errors.append("invalid execution_kind")
    try:
        started = parse_utc(manifest.get("started_at"))
        finished = parse_utc(manifest.get("finished_at"))
        if finished < started:
            errors.append("evidence finished_at precedes started_at")
    except ValidationError as exc:
        errors.append(str(exc))
    identities: list[str] = []
    for field, expected_role in (("executor", "executor"), ("verifier", "independent-verifier")):
        identity = manifest.get(field)
        if not isinstance(identity, dict):
            errors.append(f"{field} must be an object")
            continue
        identifier = identity.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{field}.id is required")
        else:
            identities.append(identifier)
        if identity.get("role") != expected_role:
            errors.append(f"{field}.role must be {expected_role}")
        if field == "verifier" and identity.get("independent") is not True:
            errors.append("verifier must be independent")
    if len(identities) == 2 and identities[0] == identities[1]:
        errors.append("executor and verifier must be different identities")
    try:
        require_string_list(
            manifest.get("authorization_refs"),
            "authorization_refs",
            minimum=1,
            unique=True,
        )
    except ValidationError as exc:
        errors.append(str(exc))
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        errors.append("files must contain immutable raw evidence")
    else:
        paths: list[str] = []
        roles: list[str] = []
        for index, item in enumerate(files):
            if not isinstance(item, dict):
                errors.append(f"files[{index}] must be an object")
                continue
            role = item.get("role")
            path = item.get("path")
            if not isinstance(role, str) or not role.strip():
                errors.append(f"files[{index}].role is required")
            else:
                roles.append(role)
            if not isinstance(path, str) or not path.strip():
                errors.append(f"files[{index}].path is required")
            else:
                paths.append(path)
            if not HEX_DIGEST_RE.fullmatch(str(item.get("sha256", ""))):
                errors.append(f"files[{index}].sha256 is invalid")
            size = item.get("bytes")
            if not isinstance(size, int) or isinstance(size, bool) or size < 1:
                errors.append(f"files[{index}].bytes must be positive")
            if item.get("immutable") is not True:
                errors.append(f"files[{index}] must be immutable")
        if len(paths) != len(set(paths)):
            errors.append("evidence file paths must be unique")
        if len(roles) != len(set(roles)):
            errors.append("evidence roles must be unique")
    corpora = manifest.get("corpora")
    if not isinstance(corpora, list):
        errors.append("corpora must be an array")
    else:
        kinds: list[str] = []
        digests: list[str] = []
        for index, item in enumerate(corpora):
            if not isinstance(item, dict):
                errors.append(f"corpora[{index}] must be an object")
                continue
            kind = item.get("kind")
            if kind not in {"development", "negative", "holdout", "representative"}:
                errors.append(f"corpora[{index}].kind is invalid")
            else:
                kinds.append(kind)
            try:
                digests.append(require_digest(item.get("digest"), f"corpora[{index}].digest"))
            except ValidationError as exc:
                errors.append(str(exc))
            if kind in {"holdout", "representative"}:
                if item.get("independent") is not True:
                    errors.append(f"{kind} corpus must be independent")
                if item.get("authoring_access") is not False:
                    errors.append(f"{kind} corpus authoring_access must be false")
        if len(kinds) != len(set(kinds)):
            errors.append("corpus kinds must be unique")
        if len(digests) != len(set(digests)):
            errors.append("corpus digests must be distinct")
    return errors


def collect_errors(prefix: str, errors: Iterable[str]) -> list[str]:
    return [f"{prefix}: {error}" for error in errors]
