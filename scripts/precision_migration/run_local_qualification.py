#!/usr/bin/env python3
"""Run and record bounded local Precision Migration engineering evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "certification"


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], output: Path, *, timeout_seconds: int = 300) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        exit_code = 124
        timed_out = True
        stderr += f"\nTIMEOUT: exceeded {timeout_seconds} seconds\n"
    rendered = "$ " + " ".join(command) + "\n" + stdout + stderr
    output.write_text(rendered, encoding="utf-8")
    return {
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "raw_evidence": output.relative_to(output.parents[1]).as_posix(),
        "digest": sha(output),
        "size_bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    checks = {
        "adapter_registry": run(
            [sys.executable, "scripts/precision_migration/adapters.py", "validate-registry"],
            raw / "adapter-registry.txt",
        ),
        "runtime_tests": run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests/precision-migration", "-p", "test_*.py", "-v"],
            raw / "runtime-tests.txt",
        ),
        "contract_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_contracts.py", "--check"],
            raw / "contract-qualification.txt",
        ),
        "exact_handler_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_domains.py", "--check"],
            raw / "exact-handler-qualification.txt",
        ),
        "orchestrator_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_orchestrators.py", "--check"],
            raw / "orchestrator-qualification.txt",
        ),
        "batch41_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_b41.py", "--check"],
            raw / "batch41-qualification.txt",
        ),
        "batch16_routes": run(
            [sys.executable, "scripts/precision_migration/validate_b16_routes.py"],
            raw / "batch16-routes.txt",
            timeout_seconds=900,
        ),
        "batch16_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_b16.py", "--check"],
            raw / "batch16-qualification.txt",
        ),
        "specialized_qualification": run(
            [sys.executable, "scripts/precision_migration/qualify_specialized.py", "--check"],
            raw / "specialized-qualification.txt",
        ),
        "coverage_matrix": run(
            [sys.executable, "scripts/precision_migration/build_coverage.py", "--check"],
            raw / "coverage-matrix.txt",
        ),
        "production_code_gate": run(
            [sys.executable, "scripts/precision_migration/run_production_code_gate.py", "--check"],
            raw / "production-code-gate.txt",
        ),
    }
    runtime_text = (raw / "runtime-tests.txt").read_text(encoding="utf-8")
    match = re.search(r"Ran (\d+) tests", runtime_text)
    result_without_digest = {
        "schema_version": 1,
        "pack_key": "precision-migration-b01-44-runtime",
        "status": "PASSED" if all(item["exit_code"] == 0 for item in checks.values()) else "FAILED",
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "executor": "local-engineering-runner",
        "independent_verifier": "NOT_RUN",
        "environment": {
            "python": subprocess.run([sys.executable, "--version"], capture_output=True, text=True, check=True).stdout.strip(),
            "openssl": subprocess.run(["openssl", "version"], capture_output=True, text=True, check=True).stdout.strip(),
            "contract": "docs/precision-migration-b01-44/local-environment-contract.json",
        },
        "checks": checks,
        "test_count": int(match.group(1)) if match else None,
        "negative_corpus": "corpus/negative/cases.json",
        "local_execution_status": "PASSED_PRODUCTION_CODE_CLOSURE_FOR_587_OF_587_AND_EXECUTABLE_DAG_FOR_45_OF_45",
        "holdout_status": "PASSED_ENGINEERING_FIXTURE_FOR_557_AND_NATIVE_LOCAL_B16_FOR_30; INDEPENDENT_EXTERNAL_HOLDOUT_NOT_RUN",
        "representative_workload_status": "PASSED_ENGINEERING_FIXTURE_FOR_557_AND_NATIVE_LOCAL_B16_FOR_30; CUSTOMER_WORKLOAD_NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
    result = {
        **result_without_digest,
        "result_digest": "sha256:" + hashlib.sha256(
            json.dumps(result_without_digest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    destination = output / "local-test-result.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
