#!/usr/bin/env python3
"""Prepare, dispatch, verify, sign and bind FRT external evidence.

The repository can automate evidence collection, but it cannot manufacture an
independent decision.  Every PASSED external record is therefore bound to an
approved run, exact repository/profile digests, privacy-minimized raw evidence,
three distinct Ed25519 signatures and check-specific zero-tolerance metrics.

External execution is delegated to an explicitly configured runner executable.
Repository or customer content never selects a shell command.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from external_campaign_parameters import validate_campaign_parameters


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "client-packs" / "frt-g01-g30-platform"
PROFILE = PACK / "acceptance" / "external-evidence-profile.json"
INSTALLED_MANIFEST = ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json"
DEFAULT_REQUEST = PACK / "certification" / "frt-gate-request.json"
EXTERNAL_EVIDENCE_PREFIX = Path(
    "client-packs/frt-g01-g30-platform/certification/external-evidence"
)

CHECK_IDS = (
    "real_source_target_builds",
    "device_matrix",
    "independent_holdout",
    "formal_proof",
    "performance",
    "chaos_dr",
    "penetration_test",
    "production_observation",
    "customer_acceptance",
)
ROLES = ("EXECUTOR", "VERIFIER", "APPROVER")
ACTOR_KEYS = {"principal_id", "organization_id"}
SIGNATURE_KEYS = {
    "algorithm",
    "key_id",
    "role",
    "signed_at",
    "payload_sha256",
    "signature_base64",
}
AUTHORIZATION_KEYS = {
    "schema_version",
    "authorization_id",
    "pack_key",
    "check_id",
    "purpose",
    "environment",
    "evidence_root",
    "runner_capability",
    "run_parameters",
    "valid_from",
    "expires_at",
    "approver",
    "signature",
}
RECORD_KEYS = {
    "schema_version",
    "record_type",
    "pack_key",
    "check_id",
    "run_id",
    "authorization_ref",
    "profile_sha256",
    "package_manifest_sha256",
    "source_tree_sha256",
    "status",
    "started_at",
    "completed_at",
    "executor",
    "verifier",
    "approver",
    "environment",
    "metrics",
    "findings",
    "claims",
    "evidence",
    "signatures",
}
EVIDENCE_KEYS = {
    "role",
    "path",
    "sha256",
    "bytes",
    "media_type",
    "classification",
    "redacted",
    "contains_personal_data",
}
ENVIRONMENT_KEYS = {
    "runner_id",
    "runner_version",
    "os",
    "architecture",
    "tool_versions",
    "region",
    "network_policy",
}
FINDING_KEYS = {"critical", "high", "medium", "low", "unresolved"}
DLP_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(rb"authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]+", re.I),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(
        rb"[\"']?(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token)[\"']?\s*[:=]\s*[\"'][^\"'\r\n]{8,}",
        re.I,
    ),
)
TEXT_MEDIA_PREFIXES = ("text/", "application/json", "application/xml", "application/yaml")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_time(value: Any, label: str, failures: list[str]) -> datetime | None:
    if not isinstance(value, str):
        failures.append(f"{label} must be an RFC3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"{label} must be an RFC3339 timestamp")
        return None
    if parsed.tzinfo is None:
        failures.append(f"{label} must include a timezone")
        return None
    return parsed.astimezone(timezone.utc)


def exact_keys(value: Any, expected: set[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    if set(value) != expected:
        return [
            f"{label} fields must be exact; missing={sorted(expected - set(value))} "
            f"unexpected={sorted(set(value) - expected)}"
        ]
    return []


def confined_file(root: Path, relative: Any, label: str) -> tuple[Path | None, list[str]]:
    if not isinstance(relative, str) or not relative:
        return None, [f"{label}.path must be a non-empty relative string"]
    path = Path(relative)
    if path.is_absolute():
        return None, [f"{label}.path must be relative"]
    resolved_root = root.resolve()
    candidate = (resolved_root / path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        return None, [f"{label}.path escapes the evidence root"]
    if not candidate.is_file():
        return None, [f"{label}.path does not resolve to a regular file"]
    return candidate, []


def validate_standard_ref(
    value: Any,
    evidence_root: Path,
    label: str,
) -> tuple[Path | None, list[str]]:
    failures = exact_keys(value, {"path", "sha256", "bytes"}, label)
    if failures:
        return None, failures
    candidate, failures = confined_file(evidence_root, value["path"], label)
    if candidate is None:
        return None, failures
    if value.get("bytes") != candidate.stat().st_size:
        failures.append(f"{label} byte count mismatch")
    if value.get("sha256") != digest_file(candidate):
        failures.append(f"{label} sha256 mismatch")
    return candidate, failures


def standard_ref(path: Path, evidence_root: Path = ROOT) -> dict[str, Any]:
    relative = path.resolve().relative_to(evidence_root.resolve()).as_posix()
    return {
        "path": relative,
        "sha256": digest_file(path),
        "bytes": path.stat().st_size,
    }


def load_profile(profile_path: Path = PROFILE) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    try:
        profile = load_json(profile_path)
    except (OSError, json.JSONDecodeError) as error:
        return {}, [f"external evidence profile is unreadable: {error}"]
    expected = {
        "schema_version",
        "profile_id",
        "pack_key",
        "version",
        "owner",
        "runner_contract",
        "independence",
        "checks",
    }
    failures.extend(exact_keys(profile, expected, "external evidence profile"))
    if profile.get("schema_version") != 1:
        failures.append("external evidence profile schema_version must be 1")
    if profile.get("pack_key") != "frt-g01-g30-platform":
        failures.append("external evidence profile pack_key mismatch")
    checks = profile.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECK_IDS):
        failures.append("external evidence profile must define exactly all FRT checks")
    return profile, failures


def load_trust_store(path: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    try:
        store = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return {}, [f"trust store is unreadable: {error}"]
    failures.extend(
        exact_keys(store, {"schema_version", "store_id", "keys"}, "trust store")
    )
    if store.get("schema_version") != 1:
        failures.append("trust store schema_version must be 1")
    keys = store.get("keys")
    if not isinstance(keys, list) or len(keys) < 3:
        failures.append("trust store must contain at least three keys")
        return store, failures
    key_ids: set[str] = set()
    for index, key in enumerate(keys):
        label = f"trust store keys[{index}]"
        expected = {
            "key_id",
            "principal_id",
            "organization_id",
            "roles",
            "public_key_path",
            "valid_from",
            "expires_at",
            "revoked",
        }
        failures.extend(exact_keys(key, expected, label))
        if not isinstance(key, dict):
            continue
        key_id = key.get("key_id")
        if not isinstance(key_id, str) or not key_id:
            failures.append(f"{label}.key_id is invalid")
        elif key_id in key_ids:
            failures.append(f"duplicate trust key: {key_id}")
        else:
            key_ids.add(key_id)
        roles = key.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or len(set(roles)) != len(roles)
            or not set(roles).issubset(ROLES)
        ):
            failures.append(f"{label}.roles is invalid")
        if key.get("revoked") not in {True, False}:
            failures.append(f"{label}.revoked must be boolean")
        public_key, key_failures = confined_file(
            path.parent,
            key.get("public_key_path"),
            f"{label}.public_key",
        )
        failures.extend(key_failures)
        if public_key is not None and b"PUBLIC KEY" not in public_key.read_bytes():
            failures.append(f"{label}.public_key is not a PEM public key")
        valid_from = parse_time(key.get("valid_from"), f"{label}.valid_from", failures)
        expires_at = parse_time(key.get("expires_at"), f"{label}.expires_at", failures)
        if valid_from and expires_at and valid_from >= expires_at:
            failures.append(f"{label} validity window is empty")
    return store, failures


def authorization_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in sorted(AUTHORIZATION_KEYS - {"signature"})}


def record_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in sorted(RECORD_KEYS - {"signatures"})}


def verify_signature(
    payload: dict[str, Any],
    envelope: Any,
    expected_role: str,
    actor: dict[str, Any],
    trust_store: dict[str, Any],
    trust_store_path: Path,
) -> list[str]:
    label = f"{expected_role} signature"
    failures = exact_keys(envelope, SIGNATURE_KEYS, label)
    if failures or not isinstance(envelope, dict):
        return failures
    if envelope.get("algorithm") != "ed25519":
        failures.append(f"{label} algorithm must be ed25519")
    if envelope.get("role") != expected_role:
        failures.append(f"{label} role mismatch")
    encoded = canonical_bytes(payload)
    expected_digest = digest_bytes(encoded)
    if envelope.get("payload_sha256") != expected_digest:
        failures.append(f"{label} payload digest mismatch")
    keys = [
        key
        for key in trust_store.get("keys", [])
        if key.get("key_id") == envelope.get("key_id")
    ]
    if len(keys) != 1:
        failures.append(f"{label} key is missing or ambiguous")
        return failures
    key = keys[0]
    if key.get("revoked") is not False:
        failures.append(f"{label} key is revoked")
    if expected_role not in key.get("roles", []):
        failures.append(f"{label} key lacks the required role")
    if key.get("principal_id") != actor.get("principal_id"):
        failures.append(f"{label} principal does not match the record actor")
    if key.get("organization_id") != actor.get("organization_id"):
        failures.append(f"{label} organization does not match the record actor")
    signed_at = parse_time(envelope.get("signed_at"), f"{label}.signed_at", failures)
    valid_from = parse_time(key.get("valid_from"), f"{label}.key.valid_from", failures)
    expires_at = parse_time(key.get("expires_at"), f"{label}.key.expires_at", failures)
    if signed_at and valid_from and signed_at < valid_from:
        failures.append(f"{label} predates key validity")
    if signed_at and expires_at and signed_at >= expires_at:
        failures.append(f"{label} is outside key validity")
    try:
        signature = base64.b64decode(
            envelope.get("signature_base64", ""), validate=True
        )
    except (ValueError, TypeError):
        failures.append(f"{label} is not valid base64")
        return failures
    public_key, key_failures = confined_file(
        trust_store_path.parent,
        key.get("public_key_path"),
        f"{label}.public_key",
    )
    failures.extend(key_failures)
    if public_key is None or failures:
        return failures
    with tempfile.TemporaryDirectory(prefix="elmos-frt-signature-") as directory:
        root = Path(directory)
        payload_path = root / "payload.json"
        signature_path = root / "signature.bin"
        payload_path.write_bytes(encoded)
        signature_path.write_bytes(signature)
        completed = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-sigfile",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
        )
    if completed.returncode != 0:
        failures.append(f"{label} cryptographic verification failed")
    return failures


def validate_actor(value: Any, label: str) -> list[str]:
    failures = exact_keys(value, ACTOR_KEYS, label)
    if not isinstance(value, dict):
        return failures
    for key in ACTOR_KEYS:
        if not isinstance(value.get(key), str) or not value[key]:
            failures.append(f"{label}.{key} must be non-empty")
    return failures


def validate_authorization(
    value: Any,
    trust_store: dict[str, Any],
    trust_store_path: Path,
    check_id: str,
    runner_capability: str,
    now: datetime | None = None,
) -> list[str]:
    failures = exact_keys(value, AUTHORIZATION_KEYS, "authorization")
    if not isinstance(value, dict):
        return failures
    if value.get("schema_version") != 1:
        failures.append("authorization schema_version must be 1")
    if value.get("pack_key") != "frt-g01-g30-platform":
        failures.append("authorization pack_key mismatch")
    if value.get("check_id") != check_id:
        failures.append("authorization check_id mismatch")
    if value.get("runner_capability") != runner_capability:
        failures.append("authorization runner capability mismatch")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
        str(value.get("authorization_id", "")),
    ):
        failures.append("authorization authorization_id is invalid")
    for field in (
        "authorization_id",
        "purpose",
        "environment",
        "evidence_root",
    ):
        if not isinstance(value.get(field), str) or not value[field]:
            failures.append(f"authorization {field} must be non-empty")
    if not isinstance(value.get("run_parameters"), dict) or not value["run_parameters"]:
        failures.append("authorization run_parameters must be a non-empty object")
    else:
        failures.extend(validate_campaign_parameters(check_id, value["run_parameters"]))
        if any(pattern.search(canonical_bytes(value["run_parameters"])) for pattern in DLP_PATTERNS):
            failures.append("authorization run_parameters contain a forbidden secret pattern")
    failures.extend(validate_actor(value.get("approver"), "authorization approver"))
    valid_from = parse_time(value.get("valid_from"), "authorization.valid_from", failures)
    expires_at = parse_time(value.get("expires_at"), "authorization.expires_at", failures)
    effective_now = now or datetime.now(timezone.utc)
    if valid_from and expires_at and valid_from >= expires_at:
        failures.append("authorization validity window is empty")
    if valid_from and expires_at and expires_at - valid_from > timedelta(hours=24):
        failures.append("authorization validity may not exceed 24 hours")
    if valid_from and effective_now < valid_from:
        failures.append("authorization is not active yet")
    if expires_at and effective_now >= expires_at:
        failures.append("authorization is expired")
    if isinstance(value.get("approver"), dict):
        failures.extend(
            verify_signature(
                authorization_payload(value),
                value.get("signature"),
                "APPROVER",
                value["approver"],
                trust_store,
                trust_store_path,
            )
        )
    return failures


def validate_evidence_item(
    value: Any,
    evidence_root: Path,
    label: str,
) -> tuple[Path | None, list[str]]:
    failures = exact_keys(value, EVIDENCE_KEYS, label)
    if not isinstance(value, dict):
        return None, failures
    candidate, path_failures = confined_file(evidence_root, value.get("path"), label)
    failures.extend(path_failures)
    if not isinstance(value.get("role"), str) or not value["role"]:
        failures.append(f"{label}.role must be non-empty")
    if not isinstance(value.get("media_type"), str) or not value["media_type"]:
        failures.append(f"{label}.media_type must be non-empty")
    if value.get("classification") not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}:
        failures.append(f"{label}.classification is invalid")
    if value.get("redacted") not in {True, False}:
        failures.append(f"{label}.redacted must be boolean")
    if value.get("contains_personal_data") is not False:
        failures.append(f"{label} may not persist personal data")
    if value.get("classification") == "CONFIDENTIAL" and value.get("redacted") is not True:
        failures.append(f"{label} confidential evidence must be redacted")
    if candidate is not None:
        if value.get("bytes") != candidate.stat().st_size or value.get("bytes", 0) <= 0:
            failures.append(f"{label} byte count mismatch or empty evidence")
        if value.get("sha256") != digest_file(candidate):
            failures.append(f"{label} sha256 mismatch")
        media_type = value.get("media_type", "")
        if candidate.stat().st_size <= 8 * 1024 * 1024 and media_type.startswith(
            TEXT_MEDIA_PREFIXES
        ):
            raw = candidate.read_bytes()
            if any(pattern.search(raw) for pattern in DLP_PATTERNS):
                failures.append(f"{label} contains a forbidden secret pattern")
    return candidate, failures


def scope_values(profile_path: Path = PROFILE) -> dict[str, str]:
    installed = load_json(INSTALLED_MANIFEST)
    return {
        "profile_sha256": digest_file(profile_path),
        "package_manifest_sha256": installed["source_package_manifest_sha256"],
        "source_tree_sha256": installed["source_tree_sha256"],
    }


def validate_metrics(
    metrics: Any,
    spec: dict[str, Any],
    failures: list[str],
) -> None:
    required = spec.get("required_metrics", [])
    if not isinstance(metrics, dict) or set(metrics) != set(required):
        failures.append(
            "metrics must contain exactly the check profile fields; "
            f"expected={sorted(required)} actual={sorted(metrics) if isinstance(metrics, dict) else []}"
        )
        return
    for key, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            failures.append(f"metric {key} must be numeric")
    for key, expected in spec.get("exact_metrics", {}).items():
        if metrics.get(key) != expected:
            failures.append(f"metric {key} must equal {expected}")
    for key, minimum in spec.get("minimum_metrics", {}).items():
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or value < minimum:
            failures.append(f"metric {key} must be at least {minimum}")
    for left, right in spec.get("equal_metric_pairs", []):
        if metrics.get(left) != metrics.get(right):
            failures.append(f"metrics {left} and {right} must be equal")
    for left, right in spec.get("less_or_equal_metric_pairs", []):
        left_value = metrics.get(left)
        right_value = metrics.get(right)
        if (
            not isinstance(left_value, (int, float))
            or not isinstance(right_value, (int, float))
            or left_value > right_value
        ):
            failures.append(f"metric {left} must not exceed {right}")


def validate_external_record(
    record_path: Path,
    trust_store_path: Path,
    *,
    evidence_root: Path = ROOT,
    profile_path: Path = PROFILE,
    enforce_pack_paths: bool = True,
    now: datetime | None = None,
    expected_scope: dict[str, str] | None = None,
) -> list[str]:
    failures: list[str] = []
    profile, profile_failures = load_profile(profile_path)
    failures.extend(profile_failures)
    trust_store, trust_failures = load_trust_store(trust_store_path)
    failures.extend(trust_failures)
    try:
        record = load_json(record_path)
    except (OSError, json.JSONDecodeError) as error:
        return failures + [f"external evidence record is unreadable: {error}"]
    failures.extend(exact_keys(record, RECORD_KEYS, "external evidence record"))
    if not isinstance(record, dict):
        return failures
    check_id = record.get("check_id")
    checks = profile.get("checks", {}) if isinstance(profile, dict) else {}
    spec = checks.get(check_id) if isinstance(checks, dict) else None
    if check_id not in CHECK_IDS or not isinstance(spec, dict):
        failures.append("external evidence record check_id is invalid")
        return failures
    if record.get("schema_version") != 1:
        failures.append("external evidence record schema_version must be 1")
    if record.get("record_type") != "FRT_EXTERNAL_EVIDENCE":
        failures.append("external evidence record_type is invalid")
    if record.get("pack_key") != "frt-g01-g30-platform":
        failures.append("external evidence record pack_key mismatch")
    if record.get("status") != "PASSED":
        failures.append("only a PASSED external evidence record can be bound")
    run_id = record.get("run_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        failures.append("external evidence record run_id is invalid")
    if enforce_pack_paths:
        try:
            relative_record = record_path.resolve().relative_to(evidence_root.resolve())
        except ValueError:
            failures.append("external evidence record escapes the evidence root")
        else:
            expected_prefix = EXTERNAL_EVIDENCE_PREFIX / str(run_id)
            if relative_record.parent != expected_prefix:
                failures.append("external evidence record is outside its run directory")
    scope = expected_scope or scope_values(profile_path)
    for field, expected in scope.items():
        if record.get(field) != expected:
            failures.append(f"external evidence record {field} mismatch")
    for role in ("executor", "verifier", "approver"):
        failures.extend(validate_actor(record.get(role), role))
    executor = record.get("executor", {})
    verifier = record.get("verifier", {})
    approver = record.get("approver", {})
    if isinstance(executor, dict) and isinstance(verifier, dict):
        if executor.get("principal_id") == verifier.get("principal_id"):
            failures.append("executor and verifier principals must differ")
        if executor.get("organization_id") == verifier.get("organization_id"):
            failures.append("executor and verifier organizations must differ")
    if isinstance(executor, dict) and isinstance(approver, dict):
        if executor.get("principal_id") == approver.get("principal_id"):
            failures.append("executor and approver principals must differ")
    if isinstance(verifier, dict) and isinstance(approver, dict):
        if verifier.get("principal_id") == approver.get("principal_id"):
            failures.append("verifier and approver principals must differ")
    started = parse_time(record.get("started_at"), "record.started_at", failures)
    completed = parse_time(record.get("completed_at"), "record.completed_at", failures)
    if started and completed and started >= completed:
        failures.append("external evidence execution window is empty")
    environment = record.get("environment")
    failures.extend(exact_keys(environment, ENVIRONMENT_KEYS, "record.environment"))
    if isinstance(environment, dict):
        if not isinstance(environment.get("tool_versions"), dict) or not environment["tool_versions"]:
            failures.append("record.environment.tool_versions must be non-empty")
        for key in ENVIRONMENT_KEYS - {"tool_versions"}:
            if not isinstance(environment.get(key), str) or not environment[key]:
                failures.append(f"record.environment.{key} must be non-empty")
    validate_metrics(record.get("metrics"), spec, failures)
    findings = record.get("findings")
    failures.extend(exact_keys(findings, FINDING_KEYS, "record.findings"))
    if isinstance(findings, dict):
        for key in FINDING_KEYS:
            if isinstance(findings.get(key), bool) or not isinstance(findings.get(key), int) or findings[key] < 0:
                failures.append(f"record.findings.{key} must be a non-negative integer")
        for key in ("critical", "high", "unresolved"):
            if findings.get(key) != 0:
                failures.append(f"record.findings.{key} must be zero")
    required_claims = set(spec.get("required_claims", []))
    claims = record.get("claims")
    if not isinstance(claims, dict) or set(claims) != required_claims:
        failures.append("claims must contain exactly the required check claims")
    elif any(value is not True for value in claims.values()):
        failures.append("every required check claim must be true")
    evidence = record.get("evidence")
    required_roles = set(spec.get("required_evidence_roles", []))
    observed_roles: list[str] = []
    if not isinstance(evidence, list):
        failures.append("record.evidence must be an array")
    else:
        for index, item in enumerate(evidence):
            _, item_failures = validate_evidence_item(
                item,
                evidence_root,
                f"record.evidence[{index}]",
            )
            failures.extend(item_failures)
            if isinstance(item, dict) and isinstance(item.get("role"), str):
                observed_roles.append(item["role"])
        if len(observed_roles) != len(set(observed_roles)):
            failures.append("record evidence roles must be unique")
        if set(observed_roles) != required_roles:
            failures.append(
                "record evidence roles must be exact; "
                f"missing={sorted(required_roles - set(observed_roles))} "
                f"unexpected={sorted(set(observed_roles) - required_roles)}"
            )
    authorization_path, authorization_ref_failures = validate_standard_ref(
        record.get("authorization_ref"),
        evidence_root,
        "record.authorization_ref",
    )
    failures.extend(authorization_ref_failures)
    if authorization_path is not None:
        try:
            authorization = load_json(authorization_path)
        except json.JSONDecodeError as error:
            failures.append(f"authorization JSON is invalid: {error}")
        else:
            effective_time = started or now
            failures.extend(
                validate_authorization(
                    authorization,
                    trust_store,
                    trust_store_path,
                    check_id,
                    spec.get("runner_capability", ""),
                    effective_time,
                )
            )
            if authorization.get("approver") != record.get("approver"):
                failures.append("authorization approver does not match record approver")
            environment_mismatch = (
                not isinstance(environment, dict)
                or authorization.get("environment") != environment.get("runner_id")
            )
            if environment_mismatch:
                failures.append("authorization environment does not match record runner_id")
            if enforce_pack_paths:
                expected_authorized_root = (EXTERNAL_EVIDENCE_PREFIX / str(run_id)).as_posix()
                if authorization.get("evidence_root") != expected_authorized_root:
                    failures.append("authorization evidence_root does not match the run directory")
            if started and completed:
                valid_from = parse_time(
                    authorization.get("valid_from"),
                    "authorization.valid_from",
                    failures,
                )
                expires_at = parse_time(
                    authorization.get("expires_at"),
                    "authorization.expires_at",
                    failures,
                )
                if valid_from and started < valid_from:
                    failures.append("record execution predates authorization")
                if expires_at and completed >= expires_at:
                    failures.append("record execution exceeds authorization")
                authorization_signed_at = parse_time(
                    authorization.get("signature", {}).get("signed_at")
                    if isinstance(authorization.get("signature"), dict)
                    else None,
                    "authorization.signature.signed_at",
                    failures,
                )
                if authorization_signed_at and authorization_signed_at > started:
                    failures.append("authorization was signed after execution started")
    signatures = record.get("signatures")
    if not isinstance(signatures, list) or len(signatures) != 3:
        failures.append("record must contain exactly three signatures")
    else:
        by_role = {
            signature.get("role"): signature
            for signature in signatures
            if isinstance(signature, dict)
        }
        if set(by_role) != set(ROLES):
            failures.append("record signatures must contain executor, verifier and approver")
        else:
            payload = record_payload(record)
            signature_times: dict[str, datetime] = {}
            for role, actor_name in (
                ("EXECUTOR", "executor"),
                ("VERIFIER", "verifier"),
                ("APPROVER", "approver"),
            ):
                actor = record.get(actor_name)
                if isinstance(actor, dict):
                    failures.extend(
                        verify_signature(
                            payload,
                            by_role[role],
                            role,
                            actor,
                            trust_store,
                            trust_store_path,
                        )
                    )
                signed_at = parse_time(
                    by_role[role].get("signed_at"),
                    f"{role} signature.signed_at",
                    failures,
                )
                if signed_at:
                    signature_times[role] = signed_at
                    if completed and signed_at < completed:
                        failures.append(f"{role} signature predates execution completion")
            if set(signature_times) == set(ROLES):
                if signature_times["VERIFIER"] < signature_times["EXECUTOR"]:
                    failures.append("verifier signed before the executor")
                if signature_times["APPROVER"] < signature_times["VERIFIER"]:
                    failures.append("approver signed before the verifier")
    return failures


def external_refs_for_record(
    record_path: Path,
    evidence_root: Path = ROOT,
) -> list[dict[str, Any]]:
    record = load_json(record_path)
    paths = [record_path]
    authorization_path, failures = confined_file(
        evidence_root,
        record["authorization_ref"]["path"],
        "record.authorization_ref",
    )
    if failures or authorization_path is None:
        raise ValueError("; ".join(failures))
    paths.append(authorization_path)
    for item in record["evidence"]:
        evidence_path, item_failures = confined_file(
            evidence_root,
            item["path"],
            f"record.evidence.{item['role']}",
        )
        if item_failures or evidence_path is None:
            raise ValueError("; ".join(item_failures))
        paths.append(evidence_path)
    unique = {path.resolve(): path for path in paths}
    return [standard_ref(path, evidence_root) for path in unique.values()]


def validate_external_check(
    check_id: str,
    item: Any,
    trust_store_path: Path | None,
    evidence_root: Path = ROOT,
) -> list[str]:
    if not isinstance(item, dict) or item.get("state") != "PASSED":
        return []
    if trust_store_path is None:
        return [f"external_checks.{check_id} PASSED requires an external trust store"]
    refs = item.get("evidence_refs")
    if not isinstance(refs, list):
        return [f"external_checks.{check_id}.evidence_refs is invalid"]
    record_paths: list[Path] = []
    ref_paths: set[str] = set()
    for index, ref in enumerate(refs):
        path, failures = validate_standard_ref(
            ref,
            evidence_root,
            f"external_checks.{check_id}.evidence_refs[{index}]",
        )
        if failures or path is None:
            continue
        ref_paths.add(ref["path"])
        if path.suffix == ".json":
            try:
                candidate = load_json(path)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(candidate, dict)
                and candidate.get("record_type") == "FRT_EXTERNAL_EVIDENCE"
                and candidate.get("check_id") == check_id
            ):
                record_paths.append(path)
    if len(record_paths) != 1:
        return [
            f"external_checks.{check_id} must reference exactly one matching external evidence record"
        ]
    failures = validate_external_record(
        record_paths[0],
        trust_store_path,
        evidence_root=evidence_root,
    )
    try:
        expected_refs = external_refs_for_record(record_paths[0], evidence_root)
    except (KeyError, TypeError, ValueError) as error:
        failures.append(f"external_checks.{check_id} record references are invalid: {error}")
    else:
        expected_paths = {ref["path"] for ref in expected_refs}
        if ref_paths != expected_paths:
            failures.append(
                f"external_checks.{check_id} refs must exactly bind record, authorization and raw evidence"
            )
    return failures


def signature_envelope(
    payload: dict[str, Any],
    private_key: Path,
    key_id: str,
    role: str,
    signed_at: str,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    encoded = canonical_bytes(payload)
    with tempfile.TemporaryDirectory(prefix="elmos-frt-sign-") as directory:
        root = Path(directory)
        payload_path = root / "payload.json"
        signature_path = root / "signature.bin"
        payload_path.write_bytes(encoded)
        completed = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(payload_path),
                "-out",
                str(signature_path),
            ],
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                "Ed25519 signing failed: "
                + completed.stderr.decode("utf-8", errors="replace")[-500:]
            )
        signature = signature_path.read_bytes()
    return {
        "algorithm": "ed25519",
        "key_id": key_id,
        "role": role,
        "signed_at": signed_at,
        "payload_sha256": digest_bytes(encoded),
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def prepare_authorization(args: argparse.Namespace) -> int:
    profile, failures = load_profile()
    if failures:
        raise SystemExit("\n".join(failures))
    spec = profile["checks"][args.check]
    now = datetime.now(timezone.utc)
    output = args.output.resolve()
    try:
        evidence_root = output.parent.relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise SystemExit("authorization output must be below the repository root") from error
    if args.valid_minutes < 1 or args.valid_minutes > 24 * 60:
        raise SystemExit("valid-minutes must be between 1 and 1440")
    parameters = load_json(args.parameters)
    if not isinstance(parameters, dict) or not parameters:
        raise SystemExit("parameters must be a non-empty JSON object")
    parameter_failures = validate_campaign_parameters(args.check, parameters)
    if parameter_failures:
        raise SystemExit("\n".join(parameter_failures))
    if any(pattern.search(canonical_bytes(parameters)) for pattern in DLP_PATTERNS):
        raise SystemExit("parameters contain a forbidden secret pattern")
    value = {
        "schema_version": 1,
        "authorization_id": f"frt-auth-{secrets.token_hex(12)}",
        "pack_key": "frt-g01-g30-platform",
        "check_id": args.check,
        "purpose": args.purpose,
        "environment": args.environment,
        "evidence_root": evidence_root,
        "runner_capability": spec["runner_capability"],
        "run_parameters": parameters,
        "valid_from": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=args.valid_minutes)).isoformat().replace(
            "+00:00", "Z"
        ),
        "approver": {
            "principal_id": args.approver,
            "organization_id": args.approver_organization,
        },
        "signature": None,
    }
    write_json(output, value)
    print(json.dumps({"authorization_template": str(output), "state": "UNSIGNED"}, indent=2))
    return 0


def sign_document(args: argparse.Namespace) -> int:
    path = args.document.resolve()
    value = load_json(path)
    signed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if args.kind == "authorization":
        if args.role != "APPROVER":
            raise SystemExit("authorization must be signed by APPROVER")
        failures = exact_keys(value, AUTHORIZATION_KEYS, "authorization")
        if failures:
            raise SystemExit("\n".join(failures))
        value["signature"] = signature_envelope(
            authorization_payload(value),
            args.private_key,
            args.key_id,
            args.role,
            signed_at,
        )
    else:
        failures = exact_keys(value, RECORD_KEYS, "external evidence record")
        if failures:
            raise SystemExit("\n".join(failures))
        signatures = value.get("signatures")
        if not isinstance(signatures, list):
            raise SystemExit("record signatures must be an array")
        if any(item.get("role") == args.role for item in signatures if isinstance(item, dict)):
            raise SystemExit(f"record already contains a {args.role} signature")
        signatures.append(
            signature_envelope(
                record_payload(value),
                args.private_key,
                args.key_id,
                args.role,
                signed_at,
            )
        )
    write_json(path, value)
    print(json.dumps({"document": str(path), "signed_role": args.role}, indent=2))
    return 0


def dispatch(args: argparse.Namespace) -> int:
    authorization_path = args.authorization.resolve()
    authorization = load_json(authorization_path)
    profile, profile_failures = load_profile()
    trust_store, trust_failures = load_trust_store(args.trust_store)
    failures = profile_failures + trust_failures
    check_id = authorization.get("check_id")
    spec = profile.get("checks", {}).get(check_id, {})
    failures.extend(
        validate_authorization(
            authorization,
            trust_store,
            args.trust_store,
            check_id,
            spec.get("runner_capability", ""),
        )
    )
    if failures:
        print("\n".join(f"BLOCKED: {failure}" for failure in failures), file=sys.stderr)
        return 2
    runner_value = args.runner or os.environ.get("ELMOS_FRT_EXTERNAL_RUNNER")
    output = args.output.resolve()
    request_path = output.with_suffix(".runner-request.json")
    if not runner_value:
        write_json(
            output,
            {
                "schema_version": 1,
                "check_id": check_id,
                "state": "NOT_RUN",
                "reason": "EXTERNAL_RUNNER_UNAVAILABLE",
            },
        )
        print(json.dumps(load_json(output), indent=2))
        return 3
    runner = Path(runner_value).resolve()
    if not runner.is_file() or not os.access(runner, os.X_OK):
        raise SystemExit("external runner must be an existing executable file")
    installed = load_json(INSTALLED_MANIFEST)
    runner_request = {
        "protocol": profile["runner_contract"]["protocol"],
        "authorization": authorization,
        "profile_ref": standard_ref(PROFILE),
        "scope": {
            "package_manifest_sha256": installed["source_package_manifest_sha256"],
            "source_tree_sha256": installed["source_tree_sha256"],
        },
        "required_evidence_roles": spec["required_evidence_roles"],
        "required_metrics": spec["required_metrics"],
        "required_claims": spec["required_claims"],
        "result_path": str(output),
    }
    write_json(request_path, runner_request)
    completed = subprocess.run(
        [
            str(runner),
            "execute",
            "--request",
            str(request_path),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        timeout=args.timeout_seconds,
        check=False,
    )
    return completed.returncode


def verify_command(args: argparse.Namespace) -> int:
    failures = validate_external_record(args.record, args.trust_store)
    result = {
        "record": str(args.record),
        "decision": "PASSED" if not failures else "REJECTED",
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


def bind_command(args: argparse.Namespace) -> int:
    failures = validate_external_record(args.record, args.trust_store)
    if failures:
        print("\n".join(f"REJECTED: {failure}" for failure in failures), file=sys.stderr)
        return 2
    record = load_json(args.record)
    request = load_json(args.request)
    request["external_checks"][record["check_id"]] = {
        "state": "PASSED",
        "evidence_refs": external_refs_for_record(args.record),
    }
    write_json(args.request, request)
    print(
        json.dumps(
            {
                "request": str(args.request),
                "bound_check": record["check_id"],
                "gate": "NOT_RUN",
                "next": (
                    "python3 scripts/frt/run_frt_gate.py "
                    f"{args.request} --external-trust-store {args.trust_store}"
                ),
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--check", choices=CHECK_IDS, required=True)
    prepare.add_argument("--purpose", required=True)
    prepare.add_argument("--environment", required=True)
    prepare.add_argument("--approver", required=True)
    prepare.add_argument("--approver-organization", required=True)
    prepare.add_argument("--parameters", type=Path, required=True)
    prepare.add_argument("--valid-minutes", type=int, default=120)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.set_defaults(func=prepare_authorization)

    sign = subparsers.add_parser("sign")
    sign.add_argument("--kind", choices=("authorization", "record"), required=True)
    sign.add_argument("--document", type=Path, required=True)
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--role", choices=ROLES, required=True)
    sign.set_defaults(func=sign_document)

    run = subparsers.add_parser("dispatch")
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--trust-store", type=Path, required=True)
    run.add_argument("--runner")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout-seconds", type=int, default=7200)
    run.set_defaults(func=dispatch)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--record", type=Path, required=True)
    verify.add_argument("--trust-store", type=Path, required=True)
    verify.set_defaults(func=verify_command)

    bind = subparsers.add_parser("bind")
    bind.add_argument("--record", type=Path, required=True)
    bind.add_argument("--trust-store", type=Path, required=True)
    bind.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    bind.set_defaults(func=bind_command)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
