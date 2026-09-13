#!/usr/bin/env python3
"""Fail-closed external evidence gate for Database and SQL modernization.

Repository-owned tests are reported as local engineering checks only. ChinaDB
production completion is accepted exclusively from an explicit external
qualification request plus an operator-pinned trust store; neither may come
from the Git checkout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TRANSPILER_SRC = ROOT / "engines/database-data-engine/sql-transpiler/src"
if str(TRANSPILER_SRC) not in sys.path:
    sys.path.insert(0, str(TRANSPILER_SRC))

DATABASE_PACK_KEYS = (
    "sqlite-3-53-3-to-postgresql-17-5",
    "postgresql-to-dm8",
    "postgresql-to-opengauss",
    "postgresql-17-5-self-service-billing",
)


def _external_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be mounted from outside the Git checkout")


def audit_database_pack(pack_key: str) -> dict[str, Any]:
    command = [
        "uv",
        "run",
        "--quiet",
        "--with",
        "jsonschema",
        "--with",
        "pyyaml",
        "python",
        str(ROOT / "scripts/batch31/run_database_gate.py"),
        str(ROOT / "database-packs" / pack_key),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "kind": "LOCAL_ENGINEERING_GATE",
        "packKey": pack_key,
        "status": "PASSED" if completed.returncode == 0 else "FAILED",
        "exitCode": completed.returncode,
        "certificationAuthority": False,
        "diagnostics": (completed.stderr or completed.stdout).strip(),
    }


def audit_manual_review_backlog() -> dict[str, Any]:
    path = ROOT / "docs/batch31/evidence/sql-manual-review-backlog.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    passed = summary.get("open") == 0 and summary.get("release_blocked") is False
    return {
        "kind": "LOCAL_BACKLOG_GATE",
        "status": "PASSED" if passed else "FAILED",
        "open": summary.get("open"),
        "total": summary.get("total"),
        "certificationAuthority": False,
    }


def audit_chinadb(
    request_path: Path,
    trust_store_path: Path,
    *,
    scope: str,
    expected_runner_attestation_digest: str,
) -> dict[str, Any]:
    from elmos_sql_transpiler.production_qualification import (
        evaluate_production_qualification,
        parse_production_qualification_json,
        parse_production_trust_store_json,
    )

    request = parse_production_qualification_json(
        _external_file(request_path, "ChinaDB request").read_bytes()
    )
    trust_store = parse_production_trust_store_json(
        _external_file(trust_store_path, "ChinaDB trust store").read_bytes()
    )
    result = evaluate_production_qualification(
        request,
        trust_store=trust_store,
        now=datetime.now(UTC),
    )
    target_results = {target["targetId"]: target for target in result["targets"]}
    required = {"dm8"} if scope == "dm8" else set(target_results)
    if not (
        expected_runner_attestation_digest.startswith("sha256:")
        and len(expected_runner_attestation_digest) == 71
        and all(
            character in "0123456789abcdef"
            for character in expected_runner_attestation_digest[7:]
        )
    ):
        raise ValueError("expected Runner attestation must be a sha256 digest")
    request_targets = {target["targetId"]: target for target in request["targets"]}
    mismatched_runner_targets = []
    for target_id in sorted(required):
        execution = request_targets[target_id].get("receipts", {}).get("execution")
        observed = None
        if isinstance(execution, dict):
            payload = execution.get("payload")
            if isinstance(payload, dict):
                performance = payload.get("performanceSummary")
                if isinstance(performance, dict):
                    observed = performance.get("runnerAttestationDigest")
        if observed != expected_runner_attestation_digest:
            mismatched_runner_targets.append(target_id)
    incomplete = {
        target_id: target_results[target_id]["state"]
        for target_id in sorted(required)
        if target_results[target_id]["state"] != "PRODUCTION_DEFINITION_OF_DONE"
    }
    for target_id in mismatched_runner_targets:
        incomplete[target_id] = "RUNNER_ATTESTATION_MISMATCH"
    return {
        "kind": "EXTERNAL_CHINADB_QUALIFICATION",
        "scope": scope,
        "status": "PASSED" if not incomplete else "FAILED",
        "requiredTargetCount": len(required),
        "completedTargetCount": len(required) - len(incomplete),
        "incompleteTargets": incomplete,
        "externalExecution": result["externalExecution"],
        "independentVerification": result["independentVerification"],
        "certification": result["certification"],
        "resultDigest": result["resultDigest"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chinadb-request", required=True, type=Path)
    parser.add_argument("--chinadb-trust-store", required=True, type=Path)
    parser.add_argument("--expected-runner-attestation-digest", required=True)
    parser.add_argument("--scope", choices=("dm8", "all"), default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        packs = [audit_database_pack(pack_key) for pack_key in DATABASE_PACK_KEYS]
        backlog = audit_manual_review_backlog()
        chinadb = audit_chinadb(
            args.chinadb_request,
            args.chinadb_trust_store,
            scope=args.scope,
            expected_runner_attestation_digest=args.expected_runner_attestation_digest,
        )
        checks = [*packs, backlog, chinadb]
        passed = all(check["status"] == "PASSED" for check in checks)
        report = {
            "schemaVersion": "1.0",
            "kind": "ELMOS_DATABASE_EXTERNAL_GATE",
            "status": "PASSED" if passed else "FAILED",
            "scope": args.scope,
            "checks": checks,
            "repositoryMaySelfCertify": False,
        }
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report = {
            "schemaVersion": "1.0",
            "kind": "ELMOS_DATABASE_EXTERNAL_GATE",
            "status": "NOT_RUN_EXTERNAL_INPUT_INVALID",
            "scope": args.scope,
            "blockers": [str(error)],
            "repositoryMaySelfCertify": False,
        }
        passed = False

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Database external gate: {report['status']} (scope={args.scope})")
        for check in report.get("checks", []):
            print(f"- {check['kind']}: {check['status']}")
        for blocker in report.get("blockers", []):
            print(f"- blocker: {blocker}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
