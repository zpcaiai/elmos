#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
SIGNED_EXTERNAL_CERTIFICATION_INTAKE_IMPLEMENTED = True
EXTERNAL_CERTIFICATION_PROMOTION_ENABLED = False
REQUIRED_EXTERNAL_CERTIFICATION_GATES = (
    "authorized_customer_repository",
    "customer_holdout",
    "customer_acceptance",
    "rootless_runner",
    "rootless_transformer",
    "rootless_verifier",
    "independent_review",
    "external_certification",
)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_file(path: Path) -> bool:
    return any(item.is_file() for item in path.rglob("*"))


def require_metric(
    failures: list[str],
    metrics: dict[str, Any],
    name: str,
    *,
    minimum: float,
) -> None:
    value = metrics.get(name)
    if not isinstance(value, int | float) or value < minimum:
        failures.append(f"{name} must be >= {minimum}")


def require_zero(failures: list[str], evidence: dict[str, Any], name: str) -> None:
    if evidence.get(name) != 0:
        failures.append(f"{name} must be zero")


def validate_evidence_refs(
    failures: list[str],
    pack: Path,
    evidence: dict[str, Any],
    pack_key: str,
) -> None:
    runs = evidence.get("runs")
    if not isinstance(runs, list) or not runs:
        failures.append("evidence runs are empty")
        return
    for reference in runs:
        if not isinstance(reference, str):
            failures.append("evidence run reference is invalid")
            continue
        path = pack / "certification" / reference
        if not path.is_file():
            failures.append(f"evidence run is missing: certification/{reference}")
            continue
        try:
            record = load(path)
        except Exception as exc:
            failures.append(f"evidence run is invalid JSON: certification/{reference}: {exc}")
            continue
        claimed_pack = record.get("pack_key")
        if claimed_pack is None and isinstance(record.get("route"), dict):
            claimed_pack = record["route"].get("pack_key")
        if claimed_pack is not None and claimed_pack != pack_key:
            failures.append(f"evidence run pack_key mismatch: certification/{reference}")


def exact_value(
    failures: list[str],
    side: dict[str, Any],
    field: str,
    label: str,
) -> str | None:
    values = side.get(field)
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
        failures.append(f"{label} must declare exactly one {field} value")
        return None
    return values[0]


def validate_test_summary(
    failures: list[str],
    summary: Any,
    label: str,
) -> int | None:
    if not isinstance(summary, dict):
        failures.append(f"{label} is missing")
        return None
    executed = summary.get("executed")
    if not isinstance(executed, int) or isinstance(executed, bool) or executed <= 0:
        failures.append(f"{label} executed must be a positive integer")
        return None
    for field in ("failures", "errors", "skipped"):
        value = summary.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            failures.append(f"{label} {field} must be zero")
    return executed


def validate_public_engineering_evidence(
    failures: list[str],
    pack: Path,
    manifest: dict[str, Any],
) -> None:
    path = pack / "certification" / "public-reference-route-evidence.json"
    if not path.is_file():
        failures.append("limited pack public engineering evidence is missing")
        return
    public = load(path)
    if public.get("evidence_class") != "LOCAL_PUBLIC_REPOSITORY_ENGINEERING":
        failures.append("public evidence class must be LOCAL_PUBLIC_REPOSITORY_ENGINEERING")
    if public.get("certification_eligible") is not False:
        failures.append("public engineering evidence must remain certification_eligible=false")

    source = manifest.get("source", {})
    target = manifest.get("target", {})
    source_framework = source.get("framework")
    target_framework = target.get("framework")
    if source_framework != "spring-boot" or target_framework != "spring-boot":
        failures.append("limited public Spring evidence requires spring-boot source and target")
    source_version = exact_value(failures, source, "framework_versions", "source")
    source_java = exact_value(failures, source, "runtime_versions", "source")
    target_version = exact_value(failures, target, "framework_versions", "target")
    target_java = exact_value(failures, target, "runtime_versions", "target")
    route = public.get("route")
    if not isinstance(route, dict):
        failures.append("public evidence route is missing")
    else:
        expected = {
            "pack_key": manifest.get("pack_key"),
            "source_spring_boot": source_version,
            "source_java": source_java,
            "target_spring_boot": target_version,
            "target_java": target_java,
        }
        for field, value in expected.items():
            if value is not None and route.get(field) != value:
                failures.append(f"public evidence route {field} mismatch")

    for field, label in (
        ("representative_public_repository", "public representative"),
        ("holdout_public_repository", "public holdout"),
    ):
        observed = public.get(field)
        if not isinstance(observed, dict):
            failures.append(f"{label} evidence is missing")
            continue
        if observed.get("customer_repository") is not False:
            failures.append(f"{label} must not be represented as a customer repository")
        if observed.get("openrewrite_actual_execution") is not True:
            failures.append(f"{label} must record actual OpenRewrite execution")
        if observed.get("download_digest_and_size_match") is not True:
            failures.append(f"{label} artifact digest and size must match")
        digest = observed.get("artifact_sha256")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            failures.append(f"{label} artifact_sha256 is invalid")
        artifact_bytes = observed.get("artifact_bytes")
        if not isinstance(artifact_bytes, int) or isinstance(artifact_bytes, bool) or artifact_bytes <= 0:
            failures.append(f"{label} artifact_bytes must be positive")
        source_count = validate_test_summary(failures, observed.get("source_tests"), f"{label} source tests")
        target_count = validate_test_summary(failures, observed.get("target_tests"), f"{label} target tests")
        if source_count is not None and target_count is not None and source_count != target_count:
            failures.append(f"{label} source and target executed test counts must match")
        verifier = observed.get("independent_verifier")
        if not isinstance(verifier, dict):
            failures.append(f"{label} verifier evidence is missing")
        else:
            if verifier.get("status") != "PASS":
                failures.append(f"{label} verifier status must be PASS")
            if verifier.get("physically_separate_process") is not True:
                failures.append(f"{label} verifier must be a physically separate process")
            if verifier.get("organizationally_independent") is not False:
                failures.append(
                    f"{label} local engineering verifier must explicitly remain organizationally_independent=false"
                )

    not_run = public.get("not_run")
    if not isinstance(not_run, dict) or not not_run:
        failures.append("public evidence must enumerate external NOT_RUN roles")
    elif any(value != "NOT_RUN" for value in not_run.values()):
        failures.append("public engineering external roles must remain NOT_RUN")


def validate_local_reference_evidence(
    failures: list[str],
    pack: Path,
    manifest: dict[str, Any],
) -> None:
    path = pack / "certification" / "local-reference-evidence.json"
    if not path.is_file():
        failures.append("local reference evidence is missing")
        return
    local = load(path)
    if local.get("pack_key") != manifest.get("pack_key"):
        failures.append("local reference evidence pack_key mismatch")
    if local.get("execution_status") != "PASSED_LOCAL":
        failures.append("local reference execution_status must be PASSED_LOCAL")
    if local.get("behavioral_parity") is not True:
        failures.append("local reference behavioral_parity must be true")
    source = local.get("source")
    target = local.get("target")
    if not isinstance(source, dict) or not isinstance(target, dict):
        failures.append("local reference source and target evidence are required")
        return
    expected_source = exact_value(failures, manifest.get("source", {}), "framework_versions", "source")
    expected_target = exact_value(failures, manifest.get("target", {}), "framework_versions", "target")
    if expected_source is not None and source.get("version") != expected_source:
        failures.append("local reference source version mismatch")
    if expected_target is not None and target.get("version") != expected_target:
        failures.append("local reference target version mismatch")
    for observed, label in ((source, "local source"), (target, "local target")):
        if observed.get("build") != "PASSED":
            failures.append(f"{label} build must be PASSED")
        runtime = observed.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("health", {}).get("status") != "UP":
            failures.append(f"{label} runtime health must be UP")
    source_responses = source.get("runtime", {}).get("responses", {})
    target_responses = target.get("runtime", {}).get("responses", {})
    if not isinstance(source_responses, dict) or not source_responses:
        failures.append("local reference must execute at least one behavior probe")
    elif source_responses != target_responses:
        failures.append("local reference source and target behavior probes differ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    validator = Path(__file__).with_name("validate_framework_pack.py")
    if subprocess.run([sys.executable, str(validator), str(pack)], check=False).returncode:
        return 1

    manifest = load(pack / "pack.json")
    support = load(pack / "support-matrix.json")
    evidence = load(pack / "certification" / "evidence.json")
    certification = load(pack / "certification" / "certification.json")
    status = str(manifest.get("status", "")).lower()
    certification_status = str(certification.get("status", "")).lower()
    failures: list[str] = []

    if certification_status != status:
        failures.append("pack and certification statuses must match")
    if not manifest.get("maintenance_owner"):
        failures.append("maintenance owner is missing")
    if not manifest.get("review_date"):
        failures.append("review date is missing")

    capabilities = support.get("capabilities", [])
    if status in {"limited", "certified"}:
        scoped_status = "certified" if status == "certified" else "supported"
        scoped = [capability for capability in capabilities if capability.get("status") == scoped_status]
        if not scoped:
            failures.append(f"{status} pack has no {scoped_status} capabilities")
        for capability in scoped:
            if not capability.get("evidence_refs"):
                failures.append(f"{scoped_status} capability lacks evidence: {capability.get('id')}")

        metrics = evidence.get("metrics", {})
        for metric, minimum in (
            ("source_fingerprint_coverage", 0.95),
            ("framework_contract_coverage", 0.95),
            ("build_green_rate", 1.0),
            ("startup_pass_rate", 1.0),
            ("p0_contract_pass_rate", 1.0),
            ("source_map_coverage", 0.95),
        ):
            require_metric(failures, metrics, metric, minimum=minimum)
        for name in ("manual_hours", "cost_per_verified_workload"):
            value = metrics.get(name)
            if not isinstance(value, int | float) or value < 0:
                failures.append(f"{name} must be a non-negative number")
        for field in (
            "critical_unknowns",
            "silent_framework_drops",
            "critical_security_regressions",
            "critical_transaction_regressions",
            "critical_data_regressions",
            "duplicate_message_or_job_effects",
            "test_integrity_violations",
        ):
            require_zero(failures, evidence, field)
        if not has_file(pack / "corpus" / "holdout"):
            failures.append("holdout corpus is empty")
        if not has_file(pack / "corpus" / "real-repository"):
            failures.append("representative repository corpus is empty")
        if not load(pack / "version-matrix.json").get("tuples"):
            failures.append("version matrix has no exact tuples")
        validate_evidence_refs(failures, pack, evidence, str(manifest.get("pack_key", "")))

    gate_results = certification.get("gate_results", {})
    if status == "limited":
        validate_local_reference_evidence(failures, pack, manifest)
        validate_public_engineering_evidence(failures, pack, manifest)
        for field in ("public_holdout", "public_representative"):
            if gate_results.get(field) != "PASSED_LOCAL_ENGINEERING":
                failures.append(f"limited pack requires {field} PASSED_LOCAL_ENGINEERING")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("limited pack must remain NOT_CERTIFIED")
        if evidence.get("external_execution_status") != "NOT_RUN":
            failures.append("limited pack must preserve external execution NOT_RUN")

    if status == "certified":
        if not SIGNED_EXTERNAL_CERTIFICATION_INTAKE_IMPLEMENTED:
            failures.append(
                "certified status is disabled until signed, content-addressed external "
                "customer/rootless/independent/certifier evidence intake is implemented"
            )
        if not EXTERNAL_CERTIFICATION_PROMOTION_ENABLED:
            failures.append(
                "certified status remains disabled: verified external intake is review-only "
                "and cannot promote a framework pack"
            )
        if evidence.get("external_execution_status") != "PASSED":
            failures.append("certified pack requires external execution PASSED")
        for field in REQUIRED_EXTERNAL_CERTIFICATION_GATES:
            if gate_results.get(field) != "PASSED":
                failures.append(f"certified pack requires {field} PASSED")

    if failures:
        print(
            "\n".join(f"GATE FAIL: {failure}" for failure in failures),
            file=sys.stderr,
        )
        return 2
    decision = "NOT_CERTIFIED" if status != "certified" else "CERTIFIED"
    print(f"GATE PASS: {manifest.get('pack_key')} status={status} decision={decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
