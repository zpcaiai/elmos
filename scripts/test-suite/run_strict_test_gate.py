#!/usr/bin/env python3
"""Authoritative fail-closed certification gate for Batch 1-37."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _common import (
    ValidationError,
    load_json,
    parse_utc,
    require_digest,
    resolve_beneath,
    sha256_file,
    sha256_json,
    validate_evidence_manifest_shape,
    validate_result_shape,
)
from validate_coverage_matrix import validate_coverage
from validate_test_catalog import validate_catalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COUNTER_KEYS = (
    "critical_unknowns",
    "critical_security_findings",
    "tenant_isolation_violations",
    "test_integrity_violations",
    "stale_evidence",
    "unreplayed_critical_failures",
    "forged_certification_attempts",
    "flaky_p0_p1",
)


def prefixed_file_digest(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def add(blockers: list[str], message: str) -> None:
    if message not in blockers:
        blockers.append(message)


def verify_control_manifest(
    root: Path,
    suite: dict[str, Any],
    schema_root: Path,
    blockers: list[str],
) -> tuple[dict[str, str], dict[str, Any] | None]:
    control_paths = {
        "catalog": resolve_beneath(root, suite.get("case_catalog", "")),
        "coverage_matrix": resolve_beneath(root, suite.get("coverage_matrix", "")),
        "strict_profile": resolve_beneath(root, suite.get("profile", "")),
        "suite": root / "suite.json",
    }
    controls = {name: prefixed_file_digest(path) for name, path in control_paths.items()}
    try:
        manifest_path = resolve_beneath(root, suite.get("case_manifest", ""))
        manifest = load_json(manifest_path)
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid case/control manifest: {exc}")
        return controls, None
    if manifest.get("manifest_version") != 2:
        add(blockers, "case/control manifest version must be 2")
    if manifest.get("suite_id") != suite.get("suite_id"):
        add(blockers, "case/control manifest suite mismatch")
    if manifest.get("control_digests") != controls:
        add(blockers, "case/control manifest control digests are stale or tampered")
    actual_schemas = {
        path.name: prefixed_file_digest(path) for path in sorted(schema_root.glob("*.json"))
    }
    if manifest.get("schema_digests") != actual_schemas:
        add(blockers, "case/control manifest schema digests are stale or tampered")
    return controls, manifest


def verify_raw_files(
    suite_root: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    blockers: list[str],
    case_id: str,
) -> dict[str, Path]:
    role_paths: dict[str, Path] = {}
    for item in manifest.get("files", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        try:
            raw = resolve_beneath(manifest_path.parent, item["path"])
            raw.relative_to(suite_root)
        except (ValidationError, ValueError) as exc:
            add(blockers, f"{case_id}: unsafe raw evidence {item.get('path')}: {exc}")
            continue
        if raw.stat().st_size != item.get("bytes"):
            add(blockers, f"{case_id}: raw evidence size mismatch for {item['path']}")
        if sha256_file(raw) != item.get("sha256"):
            add(blockers, f"{case_id}: raw evidence digest mismatch for {item['path']}")
        role = item.get("role")
        if isinstance(role, str):
            role_paths[role] = raw
    return role_paths


def verify_evidence(
    suite_root: Path,
    case: dict[str, Any],
    result_path: Path,
    result: dict[str, Any],
    catalog_digest: str,
    now: datetime,
    max_age_days: int,
    blockers: list[str],
) -> tuple[list[str], set[str]]:
    case_id = case["id"]
    manifest_digests: list[str] = []
    verifier_ids: set[str] = set()
    aggregate_roles: set[str] = set()
    aggregate_corpora: dict[str, str] = {}
    artifact_bound = False
    environment_bound = False
    for reference in result.get("evidence", []):
        try:
            manifest_path = resolve_beneath(suite_root, reference)
            manifest = load_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            add(blockers, f"{case_id}: invalid evidence reference {reference}: {exc}")
            continue
        manifest_digests.append(prefixed_file_digest(manifest_path))
        for error in validate_evidence_manifest_shape(manifest):
            add(blockers, f"{case_id}: {error}")
        if manifest.get("case_id") != case_id:
            add(blockers, f"{case_id}: evidence case mismatch")
        if manifest.get("case_digest") != sha256_json(case):
            add(blockers, f"{case_id}: evidence case digest mismatch")
        if manifest.get("catalog_digest") != catalog_digest:
            add(blockers, f"{case_id}: evidence catalog digest mismatch")
        if manifest.get("artifact_digest") != result.get("artifact_digest"):
            add(blockers, f"{case_id}: evidence artifact digest mismatch")
        if manifest.get("environment_digest") != result.get("environment_digest"):
            add(blockers, f"{case_id}: evidence environment digest mismatch")
        if manifest.get("execution_kind") != result.get("execution_kind"):
            add(blockers, f"{case_id}: evidence execution_kind mismatch")
        if manifest.get("started_at") != result.get("started_at") or manifest.get("finished_at") != result.get("finished_at"):
            add(blockers, f"{case_id}: evidence timestamps differ from result")
        try:
            finished = parse_utc(manifest.get("finished_at"))
            if finished > now + timedelta(minutes=5):
                add(blockers, f"{case_id}: evidence timestamp is in the future")
            if now - finished > timedelta(days=max_age_days):
                add(blockers, f"{case_id}: stale evidence")
        except ValidationError:
            pass
        verifier = manifest.get("verifier", {})
        if isinstance(verifier, dict) and isinstance(verifier.get("id"), str):
            verifier_ids.add(verifier["id"])
        role_paths = verify_raw_files(suite_root, manifest_path, manifest, blockers, case_id)
        aggregate_roles.update(role_paths)
        artifact_path = role_paths.get("artifact-digest")
        if artifact_path is not None:
            artifact_bound = prefixed_file_digest(artifact_path) == result.get("artifact_digest")
            if not artifact_bound:
                add(blockers, f"{case_id}: artifact digest is not bound to artifact-digest evidence")
        environment_path = role_paths.get("environment-binding")
        if environment_path is not None:
            environment_bound = prefixed_file_digest(environment_path) == result.get("environment_digest")
            if not environment_bound:
                add(blockers, f"{case_id}: environment digest is not bound to environment evidence")
        for corpus in manifest.get("corpora", []):
            if isinstance(corpus, dict) and isinstance(corpus.get("kind"), str):
                aggregate_corpora[corpus["kind"]] = corpus.get("digest", "")

    required_roles = set(case.get("evidence_required", []))
    missing_roles = sorted(required_roles - aggregate_roles)
    if missing_roles:
        add(blockers, f"{case_id}: missing required evidence roles {missing_roles}")
    if not artifact_bound:
        add(blockers, f"{case_id}: no valid artifact binding")
    if not environment_bound:
        add(blockers, f"{case_id}: no valid environment binding")
    if case.get("holdout_required"):
        if result.get("holdout_passed") is not True:
            add(blockers, f"{case_id}: holdout result is not passed")
        if "holdout" not in aggregate_corpora:
            add(blockers, f"{case_id}: independent holdout corpus evidence is missing")
    if case.get("representative_workload_required"):
        if result.get("representative_workload_passed") is not True:
            add(blockers, f"{case_id}: representative workload is not passed")
        if "representative" not in aggregate_corpora:
            add(blockers, f"{case_id}: representative corpus evidence is missing")
    if len(set(aggregate_corpora.values())) != len(aggregate_corpora):
        add(blockers, f"{case_id}: development/holdout/representative corpora are not independent")
    return sorted(manifest_digests), verifier_ids


def validate_request_shape(request: Any) -> list[str]:
    if not isinstance(request, dict):
        return ["certification request must be an object"]
    required = {
        "request_version",
        "suite_id",
        "requested_at",
        "expires_at",
        "signer_id",
        "authorization_refs",
        "control_digests",
        "case_bindings",
    }
    errors = [f"certification request missing {sorted(required-set(request))}"] if required - set(request) else []
    if request.get("request_version") != 1:
        errors.append("certification request version must be 1")
    if request.get("suite_id") != "batch1-37-strict":
        errors.append("certification request suite mismatch")
    if not isinstance(request.get("signer_id"), str) or not request.get("signer_id"):
        errors.append("certification request signer_id is required")
    if not isinstance(request.get("authorization_refs"), list) or not request.get("authorization_refs"):
        errors.append("certification request authorization_refs are required")
    if not isinstance(request.get("case_bindings"), list):
        errors.append("certification request case_bindings must be an array")
    return errors


def verify_certification_request(
    suite_root: Path,
    request_path: Path,
    signature_path: Path,
    trust_store_path: Path,
    controls: dict[str, str],
    expected_bindings: list[dict[str, Any]],
    verifier_ids: set[str],
    now: datetime,
    blockers: list[str],
) -> bool:
    try:
        request_path.resolve().relative_to(suite_root)
        signature_path.resolve().relative_to(suite_root)
        request = load_json(request_path)
        trust_store = load_json(trust_store_path)
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid certification request inputs: {exc}")
        return False
    for error in validate_request_shape(request):
        add(blockers, error)
    if request.get("control_digests") != controls:
        add(blockers, "certification request control digests mismatch")
    if request.get("case_bindings") != expected_bindings:
        add(blockers, "certification request does not bind the exact 408 result/evidence sets")
    signer_id = request.get("signer_id")
    if verifier_ids != {signer_id}:
        add(blockers, "certification signer must be the independent verifier on every passed case")
    try:
        requested_at = parse_utc(request.get("requested_at"))
        expires_at = parse_utc(request.get("expires_at"))
        if requested_at > now + timedelta(minutes=5):
            add(blockers, "certification request timestamp is in the future")
        if expires_at <= requested_at or now > expires_at:
            add(blockers, "certification request is expired or has an invalid interval")
    except ValidationError as exc:
        add(blockers, f"invalid certification request timestamp: {exc}")

    authorities = trust_store.get("authorities", []) if isinstance(trust_store, dict) else []
    anchors = [item for item in authorities if isinstance(item, dict) and item.get("signer_id") == signer_id]
    if len(anchors) != 1:
        add(blockers, "exactly one non-revoked trust anchor is required for the signer")
        return False
    anchor = anchors[0]
    if anchor.get("revoked") is not False or "independent-certifier" not in anchor.get("roles", []):
        add(blockers, "certification trust anchor is revoked or lacks independent-certifier role")
    if anchor.get("algorithm") != "rsa-sha256":
        add(blockers, "only rsa-sha256 certification signatures are accepted")
    try:
        valid_from = parse_utc(anchor.get("valid_from"))
        valid_until = parse_utc(anchor.get("valid_until"))
        if not valid_from <= now <= valid_until:
            add(blockers, "certification trust anchor is outside its validity interval")
        public_key = resolve_beneath(trust_store_path.parent, anchor.get("public_key", ""))
        if sha256_file(public_key) != anchor.get("public_key_sha256"):
            add(blockers, "trust-anchor public key digest mismatch")
            return False
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"invalid trust anchor: {exc}")
        return False
    completed = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key),
            "-signature",
            str(signature_path),
            str(request_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        add(blockers, "certification request signature verification failed")
        return False
    return not blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", default="test-suites/batch1-37-strict")
    parser.add_argument("--schema-root", default=str(REPOSITORY_ROOT / "schemas/test-suite"))
    parser.add_argument("--skill-root", default=str(REPOSITORY_ROOT / ".agents/skills"))
    parser.add_argument("--certification-request")
    parser.add_argument("--signature")
    parser.add_argument("--trust-store")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.suite).resolve()
    schema_root = Path(args.schema_root).resolve()
    now = datetime.now(timezone.utc)
    blockers: list[str] = []

    try:
        suite = load_json(root / "suite.json")
        catalog_path = resolve_beneath(root, suite.get("case_catalog", ""))
        coverage_path = resolve_beneath(root, suite.get("coverage_matrix", ""))
        profile_path = resolve_beneath(root, suite.get("profile", ""))
        catalog = load_json(catalog_path)
        profile = load_json(profile_path)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot load suite controls: {exc}", file=sys.stderr)
        return 2

    for error in validate_catalog(catalog_path, Path(args.skill_root)):
        add(blockers, f"catalog: {error}")
    for error in validate_coverage(coverage_path, catalog_path):
        add(blockers, f"coverage: {error}")
    try:
        controls, control_manifest = verify_control_manifest(root, suite, schema_root, blockers)
    except Exception as exc:  # noqa: BLE001
        add(blockers, f"control verification failed: {exc}")
        controls = {}
        control_manifest = None
    if control_manifest is not None:
        if control_manifest.get("case_count") != len(catalog.get("cases", [])):
            add(blockers, "case/control manifest case count mismatch")
        if control_manifest.get("case_ids") != [case.get("id") for case in catalog.get("cases", [])]:
            add(blockers, "case/control manifest case ids mismatch")

    thresholds = profile.get("thresholds", {})
    max_age_days = int(thresholds.get("max_evidence_age_days", 0) or 0)
    if max_age_days <= 0:
        add(blockers, "strict profile max_evidence_age_days must be positive")
        max_age_days = 0
    counts = {status: 0 for status in ("passed", "failed", "blocked", "not-run", "waived", "missing", "invalid")}
    totals = {key: 0 for key in COUNTER_KEYS}
    trace_values: list[float] = []
    source_trace_values: list[float] = []
    affected_recall: list[float] = []
    mutation_scores: list[float] = []
    p95_regs: list[float] = []
    p99_regs: list[float] = []
    resource_regs: list[float] = []
    recovery_rates: list[float] = []
    expected_bindings: list[dict[str, Any]] = []
    verifier_ids: set[str] = set()
    catalog_digest = prefixed_file_digest(catalog_path)

    for case in catalog.get("cases", []):
        case_id = case.get("id", "<unknown>")
        result_path = root / "results" / f"{case_id}.json"
        if not result_path.is_file():
            counts["missing"] += 1
            add(blockers, f"missing result {case_id}")
            continue
        try:
            result = load_json(result_path)
        except Exception as exc:  # noqa: BLE001
            counts["invalid"] += 1
            add(blockers, f"invalid result {case_id}: {exc}")
            continue
        shape_errors = validate_result_shape(result)
        if shape_errors:
            counts["invalid"] += 1
            for error in shape_errors:
                add(blockers, f"{case_id}: {error}")
        status = result.get("status")
        if status in counts:
            counts[status] += 1
        else:
            counts["invalid"] += 1
        if result.get("case_id") != case_id:
            add(blockers, f"{case_id}: result case mismatch")
        if case.get("severity") in {"P0", "P1"} and status != "passed":
            add(blockers, f"{case.get('severity')} {case_id} is {status}")
        for key in COUNTER_KEYS:
            value = result.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                add(blockers, f"{case_id}: {key} must be a non-negative integer")
                continue
            totals[key] += value
        if status == "failed" and case.get("severity") in {"P0", "P1"} and not result.get("replay_command"):
            totals["unreplayed_critical_failures"] += 1
        if status != "passed":
            continue

        try:
            require_digest(result.get("artifact_digest"), "artifact_digest")
            require_digest(result.get("environment_digest"), "environment_digest")
        except ValidationError as exc:
            add(blockers, f"{case_id}: {exc}")
        trace = float(result.get("trace_coverage", -1))
        source_trace = float(result.get("source_target_trace_coverage", -1))
        trace_values.append(trace)
        source_trace_values.append(source_trace)
        if trace < thresholds.get("evidence_trace_coverage", 1):
            add(blockers, f"{case_id}: evidence trace coverage below threshold")
        if source_trace < thresholds.get("source_target_trace_coverage", 1):
            add(blockers, f"{case_id}: source-target trace coverage below threshold")
        if "affected_test_recall" in result:
            value = float(result["affected_test_recall"])
            affected_recall.append(value)
            if value < thresholds.get("affected_test_recall", 1):
                add(blockers, f"{case_id}: affected-test recall below threshold")
        if "mutation_score" in result:
            value = float(result["mutation_score"])
            mutation_scores.append(value)
            if value < thresholds.get("mutation_score", 1):
                add(blockers, f"{case_id}: mutation score below threshold")
        if case.get("skill") == "tst-test-selection-flakiness-integrity":
            if "affected_test_recall" not in result or "mutation_score" not in result:
                add(blockers, f"{case_id}: test-integrity metrics are required")
        for key, collection, threshold_key in (
            ("p95_latency_regression", p95_regs, "p95_latency_regression_max"),
            ("p99_latency_regression", p99_regs, "p99_latency_regression_max"),
            ("resource_regression", resource_regs, "resource_regression_max"),
        ):
            if key in result:
                value = float(result[key])
                collection.append(value)
                if value > thresholds.get(threshold_key, 0):
                    add(blockers, f"{case_id}: {key} exceeds threshold")
        if case.get("skill") == "tst-performance-capacity-cost" and not all(
            key in result for key in ("p95_latency_regression", "p99_latency_regression", "resource_regression")
        ):
            add(blockers, f"{case_id}: performance regression metrics are required")
        if case.get("test_type") in {"dependency_failure", "replay_idempotency"} or case.get("skill") == "tst-chaos-dr-recovery":
            if "recovery_success_rate" not in result:
                add(blockers, f"{case_id}: recovery_success_rate is required")
            else:
                value = float(result["recovery_success_rate"])
                recovery_rates.append(value)
                if value < thresholds.get("recovery_success_rate", 1):
                    add(blockers, f"{case_id}: recovery success below threshold")
        evidence_digests, case_verifiers = verify_evidence(
            root,
            case,
            result_path,
            result,
            catalog_digest,
            now,
            max_age_days,
            blockers,
        )
        verifier_ids.update(case_verifiers)
        expected_bindings.append(
            {
                "case_id": case_id,
                "result_digest": prefixed_file_digest(result_path),
                "evidence_manifest_digests": evidence_digests,
            }
        )

    for key in COUNTER_KEYS:
        allowed = int(thresholds.get(key, 0) or 0)
        if totals[key] > allowed:
            add(blockers, f"{key} {totals[key]} exceeds {allowed}")

    supplied_request_args = [args.certification_request, args.signature, args.trust_store]
    certification_requested = any(supplied_request_args)
    valid_request = False
    if certification_requested and not all(supplied_request_args):
        add(blockers, "certification requires request, signature, and external trust store together")
    elif certification_requested:
        valid_request = verify_certification_request(
            root,
            Path(args.certification_request).resolve(),
            Path(args.signature).resolve(),
            Path(args.trust_store).resolve(),
            controls,
            expected_bindings,
            verifier_ids,
            now,
            blockers,
        )
    elif counts["passed"]:
        add(blockers, "passed results lack an externally trusted signed certification request")

    decision = "CERTIFIED" if not blockers and valid_request and counts["passed"] == 408 else "BLOCKED"
    status = "passed" if decision == "CERTIFIED" else ("failed" if counts["failed"] or counts["invalid"] or totals["test_integrity_violations"] else "blocked")
    if decision == "CERTIFIED":
        field_status = "PASSED"
    elif counts["failed"] or counts["invalid"] or totals["test_integrity_violations"]:
        field_status = "FAILED"
    else:
        field_status = "NOT_RUN"
    evidence_input = {
        "controls": controls,
        "counts": counts,
        "totals": totals,
        "bindings": expected_bindings,
        "blockers": blockers,
        "certification_requested": certification_requested,
    }
    gate = {
        "gate_id": "batch1-37-strict",
        "gate_version": 2,
        "status": status,
        "decision": decision,
        "certification_requested": certification_requested,
        "field_evidence_status": field_status,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "control_digests": controls,
        "metrics": {
            "counts": counts,
            **totals,
            "mean_trace_coverage": sum(trace_values) / len(trace_values) if trace_values else 0,
            "mean_source_target_trace_coverage": sum(source_trace_values) / len(source_trace_values) if source_trace_values else 0,
            "minimum_affected_test_recall": min(affected_recall) if affected_recall else None,
            "minimum_mutation_score": min(mutation_scores) if mutation_scores else None,
            "maximum_p95_latency_regression": max(p95_regs) if p95_regs else None,
            "maximum_p99_latency_regression": max(p99_regs) if p99_regs else None,
            "maximum_resource_regression": max(resource_regs) if resource_regs else None,
            "minimum_recovery_success_rate": min(recovery_rates) if recovery_rates else None,
        },
        "blockers": blockers,
        "evidence_digest": sha256_json(evidence_input),
        "gate_code_digest": prefixed_file_digest(Path(__file__)),
    }
    output = Path(args.output).resolve() if args.output else root / "release-gate.json"
    output.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if decision == "CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
