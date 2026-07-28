#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


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
        validate_evidence_refs(failures, pack, evidence)

    gate_results = certification.get("gate_results", {})
    if status == "limited":
        for field in ("public_holdout", "public_representative"):
            if gate_results.get(field) != "PASSED_LOCAL_ENGINEERING":
                failures.append(f"limited pack requires {field} PASSED_LOCAL_ENGINEERING")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("limited pack must remain NOT_CERTIFIED")
        if evidence.get("external_execution_status") != "NOT_RUN":
            failures.append("limited pack must preserve external execution NOT_RUN")

    if status == "certified":
        if evidence.get("external_execution_status") != "PASSED":
            failures.append("certified pack requires external execution PASSED")
        for field in (
            "authorized_customer_repository",
            "customer_holdout",
            "rootless_runner",
            "rootless_transformer",
            "rootless_verifier",
            "independent_review",
        ):
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
