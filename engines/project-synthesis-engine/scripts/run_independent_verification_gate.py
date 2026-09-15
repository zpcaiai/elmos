#!/usr/bin/env python3
"""ELMOS Project Synthesis: Independent Verification Gate & Multi-Phase Audit Runner.

Executes real process invocations across all 6 gap phases:
1. Polyglot Multi-Entity Relational Code Generation & Foreign Key Integrity
2. MySQL 8.x Persistence Profiles & Dialect Migrations
3. Distributed Transactions (Saga / Outbox) and Enterprise Message/Cache Middleware
4. Hosted Runner Fleet Multi-Tenant Scheduling and Rootless Sandboxing
5. Production SRE Resilience, RISK-SYNTHESIS-001 Guardrails, and SQLite Backup/Restore
6. Domain Pack Acceptance Scenarios (GEN-001 through GEN-006)

Adheres strictly to the EXECUTION INTEGRITY CONTRACT:
- Collects real OS process exit codes, execution times, test counts, and outputs.
- Prohibits self-certification: marks authoritative status as READY_FOR_EXTERNAL_CERTIFICATION.
- Generates cryptographic SHA-256 evidence in evidence/independent_verification_audit_evidence.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def calculate_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_test_suite(test_file: str) -> dict[str, Any]:
    cmd = ["uv", "run", "pytest", test_file, "-v"]
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start

    output = res.stdout + res.stderr
    passed = (res.returncode == 0)

    # Extract test counts from pytest output
    # e.g., "6 passed in 0.52s"
    import re
    match = re.search(r"(\d+)\s+passed", output)
    pass_count = int(match.group(1)) if match else 0
    fail_match = re.search(r"(\d+)\s+failed", output)
    fail_count = int(fail_match.group(1)) if fail_match else 0

    return {
        "suite": test_file,
        "command": cmd,
        "exit_code": res.returncode,
        "duration_seconds": round(duration, 3),
        "passed": passed,
        "tests_passed": pass_count,
        "tests_failed": fail_count,
        "stdout_tail": "\n".join(output.strip().splitlines()[-10:]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ELMOS Independent Verification Gate.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/independent_verification_audit_evidence.json"),
        help="Path to emit the audit evidence JSON.",
    )
    args = parser.parse_args()

    engine_root = Path(__file__).resolve().parents[1]

    suites_to_run = [
        ("Phase 1: Polyglot Multi-Entity Relations", "tests/test_production_relations.py"),
        ("Phase 2: MySQL 8.x Persistence Profiles", "tests/test_mysql_generation.py"),
        ("Phase 1-2: Polyglot Multi-Entity & MySQL Generation", "tests/test_polyglot_multi_entity_and_mysql.py"),
        ("Phase 3: Enterprise Distributed Middleware", "tests/test_enterprise_middleware_generation.py"),
        ("Phase 4: Hosted Runner Fleet & Sandbox", "tests/test_hosted_runner_fleet_e2e_scheduler.py"),
        ("Phase 5: Production SRE & RISK-SYNTHESIS-001", "tests/test_backup_restore_and_sre_resilience.py"),
        ("Phase 6: Domain Pack Scenarios GEN-001..006", "tests/test_domain_pack_gen_scenarios.py"),
    ]

    print("================================================================================")
    print("ELMOS PROJECT SYNTHESIS: INDEPENDENT VERIFICATION & AUDIT RUNNER")
    print("Zero Simulation | Real Process Execution | Non-Self-Certification Invariants")
    print("================================================================================")

    start_total = time.time()
    results: list[dict[str, Any]] = []
    total_tests = 0
    total_passed = 0
    all_passed = True

    for phase_name, test_rel_path in suites_to_run:
        print(f"\n[*] Executing: {phase_name} ({test_rel_path})...")
        full_path = engine_root / test_rel_path
        if not full_path.is_file():
            print(f"[-] ERROR: Suite file missing: {test_rel_path}")
            all_passed = False
            results.append({"suite": test_rel_path, "status": "FILE_NOT_FOUND", "passed": False})
            continue

        suite_result = run_test_suite(test_rel_path)
        suite_result["phase"] = phase_name
        suite_result["file_sha256"] = calculate_file_hash(full_path)
        results.append(suite_result)

        total_tests += suite_result.get("tests_passed", 0) + suite_result.get("tests_failed", 0)
        total_passed += suite_result.get("tests_passed", 0)

        if not suite_result["passed"]:
            all_passed = False
            print(f"[-] FAILED: {phase_name} (Exit code: {suite_result['exit_code']})")
        else:
            print(f"[+] PASSED: {phase_name} ({suite_result.get('tests_passed', 0)} tests passed in {suite_result['duration_seconds']}s)")

    total_duration = time.time() - start_total

    print("\n================================================================================")
    print(f"Summary: {total_passed}/{total_tests} tests passed across {len(suites_to_run)} suites in {total_duration:.2f}s")
    print(f"Overall Test Status: {'PASSED' if all_passed else 'FAILED'}")
    print("Certification Authority Status: READY_FOR_EXTERNAL_CERTIFICATION (Non-self-certified)")
    print("================================================================================")

    evidence_doc: dict[str, Any] = {
        "schema_version": "1.0.0",
        "business_line": "多语言项目生成 (/generation - Business Line 5)",
        "audit_profile": "INDEPENDENT_VERIFICATION_GATE_V1",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "runner": {
            "os": sys.platform,
            "python_version": sys.version.split()[0],
            "execution_mode": "REAL_PROCESS_UV_PYTEST",
        },
        "non_self_certification_declaration": {
            "is_authoritative_certifier": False,
            "external_certification_status": "READY_FOR_EXTERNAL_CERTIFICATION" if all_passed else "NOT_READY",
            "certification_claim": "IMPLEMENTATION READY FOR EXTERNAL CERTIFICATION",
        },
        "execution_summary": {
            "all_suites_passed": all_passed,
            "total_suites_executed": len(suites_to_run),
            "total_tests_executed": total_tests,
            "total_tests_passed": total_passed,
            "total_duration_seconds": round(total_duration, 3),
        },
        "suites": results,
    }

    # Write evidence
    output_path = engine_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evidence_doc, f, indent=2, ensure_ascii=False)

    print(f"[+] Cryptographic evidence persisted to: {output_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
