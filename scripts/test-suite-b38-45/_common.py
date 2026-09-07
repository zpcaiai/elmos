#!/usr/bin/env python3
"""Shared fail-closed helpers for the Batch 38-45 strict suite."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CASE_ID_RE = re.compile(r"^(?:B(?:3[8-9]|4[0-5])-\d{3}|X-U\d{3}-\d{3})$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
ZERO_DIGEST = "sha256:" + "0" * 64
STATUSES = {"passed", "failed", "blocked", "not-run", "waived"}
PRIORITIES = {"P0", "P1", "P2"}
CATEGORIES = {
    "success",
    "boundary",
    "negative",
    "dependency-failure",
    "security",
    "replay-idempotency",
    "version-drift",
    "evidence-tamper",
    "recovery",
    "performance",
    "privacy",
    "governance",
}
REQUIRED_EVIDENCE_ROLES = {
    "artifact-binding",
    "environment-binding",
    "execution-log",
    "execution-result",
    "provenance",
    "verification",
    "replay-script",
    "holdout-attestation",
    "representative-attestation",
}
CASE_REQUIRED = {
    "case_id",
    "skill_code",
    "skill_name",
    "batch",
    "product_skill_ids",
    "title",
    "priority",
    "category",
    "preconditions",
    "steps",
    "assertions",
    "expected",
    "evidence_required",
    "anti_cheat",
    "zero_tolerance",
    "required_real_system",
    "holdout_required",
    "representative_workload_required",
    "replayable",
    "timeout_seconds",
    "retries",
    "tags",
}
RESULT_REQUIRED = {
    "case_id",
    "status",
    "artifact_digest",
    "environment_digest",
    "started_at",
    "finished_at",
    "execution_kind",
    "evidence",
    "replay_command",
    "trace_coverage",
    "authorization_refs",
    "counters",
    "findings",
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
    "replay_command",
    "files",
    "corpora",
}


class ValidationError(ValueError):
    """Raised for malformed or unsafe suite inputs."""


def load_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_file(path: Path | str, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


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


def parse_utc(value: Any) -> datetime:
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
    value: Any, label: str, *, minimum: int = 1, unique: bool = False
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValidationError(f"{label} must contain at least {minimum} item(s)")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{label} must contain non-empty strings")
    if unique and len(value) != len(set(value)):
        raise ValidationError(f"{label} must not contain duplicates")
    return value


def validate_case(case: Any) -> list[str]:
    if not isinstance(case, dict):
        return ["case must be an object"]
    errors: list[str] = []
    missing = CASE_REQUIRED - set(case)
    if missing:
        errors.append(f"missing fields {sorted(missing)}")
    extra = set(case) - CASE_REQUIRED
    if extra:
        errors.append(f"unexpected fields {sorted(extra)}")
    if not isinstance(case.get("case_id"), str) or not CASE_ID_RE.fullmatch(case["case_id"]):
        errors.append("invalid case_id")
    if not isinstance(case.get("skill_name"), str) or not SKILL_NAME_RE.fullmatch(case["skill_name"]):
        errors.append("invalid skill_name")
    if not re.fullmatch(r"U\d{3}", str(case.get("skill_code", ""))):
        errors.append("invalid skill_code")
    batch = case.get("batch")
    if batch != "cross" and (not isinstance(batch, int) or isinstance(batch, bool) or not 38 <= batch <= 45):
        errors.append("batch must be cross or an integer from 38 through 45")
    product_ids = case.get("product_skill_ids")
    if not isinstance(product_ids, list) or any(
        not isinstance(item, int) or isinstance(item, bool) or not 1325 <= item <= 1496
        for item in product_ids
    ) or len(product_ids) != len(set(product_ids)):
        errors.append("product_skill_ids must contain unique Skills 1325 through 1496")
    if batch == "cross" and product_ids:
        errors.append("cross-cutting cases cannot claim direct product Skill ownership")
    if batch != "cross" and not product_ids:
        errors.append("Batch-specific cases require product_skill_ids")
    if case.get("priority") not in PRIORITIES:
        errors.append("invalid priority")
    if case.get("category") not in CATEGORIES:
        errors.append("invalid category")
    for field, minimum in (
        ("preconditions", 2),
        ("steps", 3),
        ("assertions", 3),
        ("expected", 3),
        ("evidence_required", len(REQUIRED_EVIDENCE_ROLES)),
        ("anti_cheat", 2),
        ("tags", 3),
    ):
        try:
            values = require_string_list(case.get(field), field, minimum=minimum, unique=True)
            if field == "evidence_required" and not REQUIRED_EVIDENCE_ROLES.issubset(values):
                errors.append("evidence_required omits mandatory evidence roles")
        except ValidationError as exc:
            errors.append(str(exc))
    for field in (
        "zero_tolerance",
        "required_real_system",
        "holdout_required",
        "representative_workload_required",
        "replayable",
    ):
        if not isinstance(case.get(field), bool):
            errors.append(f"{field} must be boolean")
    if case.get("holdout_required") is not True or case.get("representative_workload_required") is not True:
        errors.append("strict certification cases require holdout and representative workloads")
    timeout = case.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
        errors.append("timeout_seconds must be a positive integer")
    retries = case.get("retries")
    if not isinstance(retries, int) or isinstance(retries, bool) or not 0 <= retries <= 2:
        errors.append("retries must be between 0 and 2")
    return errors


def validate_result_shape(result: Any) -> list[str]:
    if not isinstance(result, dict):
        return ["result must be an object"]
    errors: list[str] = []
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
    if not isinstance(evidence, list) or any(not isinstance(item, str) or not item for item in evidence):
        errors.append("evidence must be an array of non-empty paths")
    if status == "not-run":
        if result.get("started_at") is not None or result.get("finished_at") is not None:
            errors.append("not-run results cannot contain timestamps")
        if result.get("execution_kind") is not None or evidence or result.get("replay_command") is not None:
            errors.append("not-run results cannot claim execution or evidence")
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
        if result.get("execution_kind") not in {"real", "approved-equivalent"}:
            errors.append("passed results require a supported execution_kind")
        if not isinstance(result.get("replay_command"), str) or not result["replay_command"].strip():
            errors.append("passed results require replay_command")
        trace = result.get("trace_coverage")
        if not isinstance(trace, (int, float)) or isinstance(trace, bool) or not 0 <= trace <= 1:
            errors.append("trace_coverage must be between zero and one")
        try:
            require_string_list(result.get("authorization_refs"), "authorization_refs", unique=True)
        except ValidationError as exc:
            errors.append(str(exc))
    counters = result.get("counters")
    if not isinstance(counters, dict) or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counters.values()
    ):
        errors.append("counters must contain non-negative integers")
    if not isinstance(result.get("findings"), list):
        errors.append("findings must be an array")
    return errors


def validate_evidence_manifest_shape(manifest: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return ["evidence manifest must be an object"]
    errors: list[str] = []
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
    for field, role in (("executor", "executor"), ("verifier", "independent-verifier")):
        identity = manifest.get(field)
        if not isinstance(identity, dict):
            errors.append(f"{field} must be an object")
            continue
        identifier = identity.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{field}.id is required")
        else:
            identities.append(identifier)
        if identity.get("role") != role:
            errors.append(f"{field}.role must be {role}")
        if field == "verifier" and identity.get("independent") is not True:
            errors.append("verifier must be independent")
    if len(identities) == 2 and identities[0] == identities[1]:
        errors.append("executor and verifier must be different identities")
    try:
        require_string_list(manifest.get("authorization_refs"), "authorization_refs", unique=True)
    except ValidationError as exc:
        errors.append(str(exc))
    if not isinstance(manifest.get("replay_command"), str) or not manifest["replay_command"].strip():
        errors.append("replay_command is required")
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
            path = item.get("path")
            role = item.get("role")
            if not isinstance(path, str) or not path:
                errors.append(f"files[{index}].path is required")
            else:
                paths.append(path)
            if not isinstance(role, str) or not role:
                errors.append(f"files[{index}].role is required")
            else:
                roles.append(role)
            try:
                require_digest(item.get("sha256"), f"files[{index}].sha256")
            except ValidationError as exc:
                errors.append(str(exc))
            size = item.get("bytes")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                errors.append(f"files[{index}].bytes must be non-negative")
        if len(paths) != len(set(paths)):
            errors.append("raw evidence paths must be unique")
        if len(roles) != len(set(roles)):
            errors.append("raw evidence roles must be unique")
    corpora = manifest.get("corpora")
    if not isinstance(corpora, list) or len(corpora) != 3:
        errors.append("corpora must contain development, holdout and representative entries")
    else:
        kinds: list[str] = []
        digests: list[str] = []
        for index, corpus in enumerate(corpora):
            if not isinstance(corpus, dict):
                errors.append(f"corpora[{index}] must be an object")
                continue
            kind = corpus.get("kind")
            kinds.append(kind)
            try:
                digests.append(require_digest(corpus.get("digest"), f"corpora[{index}].digest"))
            except ValidationError as exc:
                errors.append(str(exc))
            if not isinstance(corpus.get("manifest_path"), str) or not corpus["manifest_path"]:
                errors.append(f"corpora[{index}].manifest_path is required")
            if not isinstance(corpus.get("attestation_ref"), str) or not corpus["attestation_ref"]:
                errors.append(f"corpora[{index}].attestation_ref is required")
            if not isinstance(corpus.get("verifier_id"), str) or not corpus["verifier_id"]:
                errors.append(f"corpora[{index}].verifier_id is required")
            if kind in {"holdout", "representative"} and corpus.get("authoring_access") is not False:
                errors.append(f"{kind} corpus must deny authoring access")
        if set(kinds) != {"development", "holdout", "representative"}:
            errors.append("corpora kinds must be exact")
        if len(digests) != len(set(digests)):
            errors.append("corpora digests must be independent")
    return errors


def collect_errors(prefix: str, errors: list[str]) -> list[str]:
    return [f"{prefix}: {error}" for error in errors]
