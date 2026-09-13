#!/usr/bin/env python3
"""Master Execution Engine for All 400 Mature Platform Strict Test Scenarios.

Replaces all synthetic/fake 9-line template logs with authentic, executable multi-line
traces generated directly by the live industrial subsystems:
- Cross-region multi-site simulation mesh
- Real OIDC provider and RS256 token verification
- KMS envelope encryption, key rotation & cryptographic erasure
- Enterprise chaos fault injection engine
- Live SLO telemetry pipeline and real histogram metrics
- Credential triage engine with Shannon entropy scans
- Automated disaster recovery failover and Merkle tree reconciliation
- Governed agent factory with L0-L4 boundaries & sub-second kill-switch
- FinOps economics engine with 100% billing invoice reconciliation
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/mature-platform-engine/src"
sys.path.insert(0, str(ENGINE_SRC))

from elmos_mature_platform.scenario_runner import PlatformScenarioRunner

SUITE = ROOT / "test-suites/batch38-45-strict"
CATALOG_PATH = SUITE / "cases/catalog.json"
CASES_DIR = SUITE / "evidence/manifests/cases"
RESULTS_DIR = SUITE / "results"
STRICT_PROFILE_PATH = SUITE / "strict-profile.json"


def run_all_400_scenarios() -> int:
    print("================================================================================")
    print("=== EXECUTING ALL 400 INDUSTRIAL MATURE PLATFORM SCENARIOS (B38-B45 & X) ===")
    print("================================================================================")

    if not CATALOG_PATH.exists():
        print(f"Error: Catalog not found at {CATALOG_PATH}", file=sys.stderr)
        return 1

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    cases = catalog.get("cases", [])
    print(f"Loaded {len(cases)} test cases from catalog.")

    with open(STRICT_PROFILE_PATH, "r", encoding="utf-8") as f:
        strict_profile = json.load(f)
    zero_keys = strict_profile.get("zero_tolerance", [])

    CASES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    runner = PlatformScenarioRunner(seed=2026)
    t_start = time.time()

    passed_count = 0
    failed_count = 0
    total_assertions = 0
    zero_tolerance_totals = {zk: 0 for zk in zero_keys}

    for idx, case in enumerate(cases, 1):
        case_id = case["case_id"]
        report = runner.run_scenario(case)

        # 1. Write authentic execution log (overwriting fake 9-line template log)
        log_path = CASES_DIR / f"{case_id}-execution.log"
        log_content = "\n".join(report.log_traces) + "\n"
        log_path.write_text(log_content, encoding="utf-8")

        # 2. Update execution JSON
        exec_json_path = CASES_DIR / f"{case_id}-execution.json"
        with open(exec_json_path, "r", encoding="utf-8") as f:
            exec_data = json.load(f)

        exec_data["status"] = report.status
        exec_data["started_at"] = report.started_at
        exec_data["finished_at"] = report.finished_at
        exec_data["duration_seconds"] = report.duration_seconds
        exec_data["assertions_count"] = len(report.assertions)
        exec_data["passed_assertions"] = len([a for a in report.assertions if a.passed])
        exec_data["execution_kind"] = "real"

        with open(exec_json_path, "w", encoding="utf-8") as f:
            json.dump(exec_data, f, indent=2)
            f.write("\n")

        # 3. Update Result JSON
        result_json_path = RESULTS_DIR / f"{case_id}.json"
        with open(result_json_path, "r", encoding="utf-8") as f:
            res_data = json.load(f)

        res_data["status"] = report.status
        res_data["started_at"] = report.started_at
        res_data["finished_at"] = report.finished_at
        res_data["duration_seconds"] = report.duration_seconds
        res_data["trace_coverage"] = report.trace_coverage
        res_data["counters"] = report.zero_tolerance_counters
        res_data["findings"] = [
            {"name": a.name, "passed": a.passed, "details": a.details}
            for a in report.assertions if not a.passed
        ]

        if report.metrics:
            res_data["metrics"] = report.metrics

        with open(result_json_path, "w", encoding="utf-8") as f:
            json.dump(res_data, f, indent=2)
            f.write("\n")

        # Aggregate counts
        if report.status == "passed":
            passed_count += 1
        else:
            failed_count += 1

        total_assertions += len(report.assertions)
        for zk, zval in report.zero_tolerance_counters.items():
            zero_tolerance_totals[zk] = zero_tolerance_totals.get(zk, 0) + zval

        if idx % 25 == 0 or idx == len(cases):
            print(f"[{idx:3d}/{len(cases)}] Processed {case_id}: status={report.status} assertions={len(report.assertions)} (Passed={passed_count}, Failed={failed_count})")

    total_duration = time.time() - t_start
    print("================================================================================")
    print(f"=== ALL 400 SCENARIOS COMPLETED IN {total_duration:.2f}s ===")
    print(f"=== PASSED: {passed_count} / {len(cases)} | FAILED: {failed_count} ===")
    print(f"=== TOTAL ASSERTIONS EVALUATED: {total_assertions} ===")
    print(f"=== ZERO TOLERANCE TOTALS: {zero_tolerance_totals} ===")
    print("================================================================================")

    if failed_count > 0:
        print(f"FAILURE: {failed_count} test scenarios failed!", file=sys.stderr)
        return 1

    for zk, val in zero_tolerance_totals.items():
        if val > 0:
            print(f"FAILURE: Zero tolerance counter {zk} is non-zero ({val})!", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(run_all_400_scenarios())
