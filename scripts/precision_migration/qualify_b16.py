#!/usr/bin/env python3
"""Materialize five-case qualification records for all 30 native B16 routes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.precision_migration.adapters import AdapterRegistry
from scripts.precision_migration.runtime import canonical_digest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "b16-qualification" / "results.json"
TEST_TYPES = ("positive", "negative", "integration", "holdout", "representative")


def file_evidence(path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def passed(skill: str, test_type: str, evidence: dict[str, Any]) -> dict[str, Any]:
    body = {"skill": skill, "test_type": test_type, "state": "PASS", "evidence": evidence}
    return {**body, "result_digest": canonical_digest(body)}


def build() -> dict[str, Any]:
    adapters = AdapterRegistry.load()
    entries = sorted(
        (entry for entry in adapters.payload["entries"] if entry["handler_id"].startswith("batch29-route-executor-v1:")),
        key=lambda item: item["skill"],
    )
    results: list[dict[str, Any]] = []
    gate_script = ROOT / "scripts" / "batch29" / "run_route_gate.py"
    for i, entry in enumerate(entries):
        route_key = entry["handler_id"].split(":", 1)[1]
        print(f"[{i+1}/{len(entries)}] qualifying {route_key}...", file=sys.stderr, flush=True)
        route = ROOT / "routes" / route_key
        evidence_path = route / "certification" / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        runs = evidence.get("runs")
        negative_runs = evidence.get("negative_runs")
        if not isinstance(runs, list) or len(runs) != 3 or not isinstance(negative_runs, list) or not negative_runs:
            raise ValueError(f"B16 route evidence inventory is incomplete: {route_key}")
        role_map = {
            "positive": route / runs[0],
            "holdout": route / runs[1],
            "representative": route / runs[2],
        }
        for role, path in role_map.items():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") != "PASSED" or payload.get("behavior_pass_rate") != 1.0:
                raise ValueError(f"B16 {role} evidence failed: {route_key}")
            results.append(passed(entry["skill"], role, file_evidence(path)))
        negative_paths = [route / reference for reference in negative_runs]
        for path in negative_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") != "PASSED" or payload.get("expected_result") != "BLOCKED":
                raise ValueError(f"B16 negative evidence failed: {route_key}")
        results.append(
            passed(
                entry["skill"],
                "negative",
                {"runs": [file_evidence(path) for path in negative_paths], "fail_closed": True},
            )
        )
        completed = subprocess.run(
            [sys.executable, str(gate_script), str(route)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(os.environ.get("ELMOS_B16_GATE_TIMEOUT_SECONDS", "300")),
        )
        if completed.returncode:
            raise ValueError(f"B16 integration gate failed: {route_key}: {(completed.stderr or completed.stdout)[-500:]}")
        results.append(
            passed(
                entry["skill"],
                "integration",
                {"route_manifest": file_evidence(route / "route.json"), "gate": "PASSED_LOCAL"},
            )
        )
    if len(entries) != 30 or len(results) != 150:
        raise ValueError(f"B16 qualification inventory mismatch: {len(entries)}/{len(results)}")
    results.sort(key=lambda item: (item["skill"], TEST_TYPES.index(item["test_type"])))
    return {
        "schema_version": 1,
        "suite": "precision-migration-b16-native-local-v1",
        "skill_count": 30,
        "result_count": 150,
        "test_types": list(TEST_TYPES),
        "all_tests_passed": True,
        "execution_scope": "NATIVE_LOCAL_ROUTE",
        "independent_verification": "NOT_RUN",
        "external_certification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("B16 qualification results drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "skills": 30, "results": 150}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
