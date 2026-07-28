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


def validate_independent_corpus(
    failures: list[str],
    route: Path,
    corpus: str,
) -> None:
    root = route / "corpus" / corpus
    if not has_file(root):
        failures.append(f"{corpus} corpus is empty")
        return
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        failures.append(f"{corpus} manifest is missing")
        return
    manifest = load(manifest_path)
    if manifest.get("corpus") != corpus:
        failures.append(f"{corpus} manifest corpus does not match")
    if manifest.get("independent") is not True:
        failures.append(f"{corpus} corpus is not marked independent")
    if manifest.get("rule_authoring_input") is not False:
        failures.append(f"{corpus} corpus was used for rule authoring")
    for field in ("source_file", "cases_file"):
        relative = manifest.get(field)
        if not isinstance(relative, str) or not (root / relative).is_file():
            failures.append(f"{corpus} {field} is missing")


def validate_evidence_refs(
    failures: list[str],
    route: Path,
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
        path = route / reference
        if not path.is_file():
            failures.append(f"evidence run is missing: {reference}")
            continue
        run = load(path)
        if run.get("status") != "PASSED":
            failures.append(f"evidence run did not pass: {reference}")
        if run.get("behavior_pass_rate") != 1.0:
            failures.append(f"behavior pass rate is not 1: {reference}")
        if run.get("critical_unknown_semantics") != 0:
            failures.append(f"critical unknown semantics remain: {reference}")
        if run.get("source_map_coverage") != 1.0:
            failures.append(f"source-map coverage is not 1: {reference}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir")
    args = parser.parse_args()
    route = Path(args.route_dir)
    validator = Path(__file__).with_name("validate_route.py")
    if subprocess.run([sys.executable, str(validator), str(route)], check=False).returncode:
        return 1

    manifest = load(route / "route.json")
    evidence = load(route / "certification" / "evidence.json")
    certification = load(route / "certification" / "certification.json")
    support = load(route / "support-matrix.json")
    status = str(manifest.get("status", "")).lower()
    certification_status = str(certification.get("status", "")).lower()
    failures: list[str] = []

    if certification_status != status:
        failures.append("route and certification statuses must match")
    if not manifest.get("maintenance_owner"):
        failures.append("maintenance owner is missing")
    if not manifest.get("review_date"):
        failures.append("review date is missing")

    capabilities = support.get("capabilities", [])
    if status in {"limited", "certified"}:
        supported_status = "certified" if status == "certified" else "supported"
        scoped = [capability for capability in capabilities if capability.get("status") == supported_status]
        if not scoped:
            failures.append(f"{status} route has no {supported_status} capabilities")
        for capability in scoped:
            if not capability.get("evidence_refs"):
                failures.append(f"{supported_status} capability lacks evidence: {capability.get('id')}")

        metrics = evidence.get("metrics", {})
        require_metric(failures, metrics, "build_green_rate", minimum=1.0)
        require_metric(failures, metrics, "p0_behavior_pass_rate", minimum=1.0)
        require_metric(failures, metrics, "source_map_coverage", minimum=0.95)
        for name in ("manual_hours", "cost_per_verified_workload"):
            value = metrics.get(name)
            if not isinstance(value, int | float) or value < 0:
                failures.append(f"{name} must be a non-negative number")
        for field in (
            "critical_unknown_semantics",
            "critical_behavior_regressions",
            "test_integrity_violations",
        ):
            require_zero(failures, evidence, field)
        if evidence.get("execution_status") != "PASSED_LOCAL":
            failures.append("local execution evidence did not pass")
        validate_independent_corpus(failures, route, "holdout")
        validate_independent_corpus(failures, route, "real-repository")
        validate_evidence_refs(failures, route, evidence)

    gate_results = certification.get("gate_results", {})
    if status == "limited":
        if gate_results.get("local_execution") != "PASSED":
            failures.append("limited route requires local execution PASSED")
        if gate_results.get("independent_verification") not in {"NOT_RUN", "PASSED"}:
            failures.append("limited route has invalid independent verification state")
        if gate_results.get("external_execution") not in {"NOT_RUN", "PASSED"}:
            failures.append("limited route has invalid external execution state")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("limited route must remain NOT_CERTIFIED")

    if status == "certified":
        if gate_results.get("independent_verification") != "PASSED":
            failures.append("certified route requires independent verification PASSED")
        if gate_results.get("external_execution") != "PASSED":
            failures.append("certified route requires external execution PASSED")

    if failures:
        print(
            "\n".join(f"GATE FAIL: {failure}" for failure in failures),
            file=sys.stderr,
        )
        return 2
    decision = "NOT_CERTIFIED" if status != "certified" else "CERTIFIED"
    print(f"GATE PASS: {manifest.get('route_key')} status={status} decision={decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
