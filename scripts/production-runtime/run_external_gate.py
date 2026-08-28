#!/usr/bin/env python3
"""Plan or execute the explicitly authorized external production gate.

The default is a no-side-effect plan. Execution requires a separately supplied
authorization object and an operator acknowledgement. Commands are constructed
from typed plan fields and run without a shell. Provider and backup/PITR actions
remain adapter-owned because their protocols and recovery semantics are not
provider-neutral.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from external_gate_contract import (
    ContractError,
    OPERATIONS,
    EXPECTED_PACKAGE_SHA256,
    load_object,
    preflight,
    redact_command,
    sha256,
    validate_authorization,
    validate_plan,
    validate_verifier_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
ACK = "I_HAVE_APPROVED_THIS_EXACT_EXTERNAL_GATE_RUN"


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_log(output_dir: Path, name: str, command: list[str], result: subprocess.CompletedProcess[str], secrets: list[str]) -> str:
    path = output_dir / f"{name}.log"
    safe_command = " ".join(redact_command(command, secrets))
    path.write_text(
        f"$ {safe_command}\n\n{result.stdout}{result.stderr}",
        encoding="utf-8",
    )
    return path.name


def run_binary(output_dir: Path, name: str, command: list[str], secrets: list[str] | None = None) -> dict[str, Any]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    log = command_log(output_dir, name, command, result, secrets or [])
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "log": log,
        "log_sha256": sha256(output_dir / log),
    }


def run_independent_verifier(operation: dict[str, Any], report_path: Path, output_dir: Path) -> dict[str, Any]:
    endpoint = os.environ[operation["endpoint_env"]]
    if urlparse(endpoint).scheme != "https":
        return {"status": "UNKNOWN", "reason": "independent verifier endpoint must use HTTPS"}
    token = os.environ[operation["credential_env"]]
    payload = report_path.read_bytes()
    report_digest = hashlib.sha256(payload).hexdigest()
    request = urllib.request.Request(endpoint, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-ELMOS-Report-SHA256", report_digest)
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(1024 * 1024)
            verifier_receipt = json.loads(body.decode("utf-8"))
    except Exception as exc:  # external outcome is explicitly UNKNOWN, never retried blindly
        return {"status": "UNKNOWN", "reason": f"independent verifier outcome is uncertain: {type(exc).__name__}"}
    try:
        verifier_receipt = validate_verifier_receipt(verifier_receipt, operation, report_digest)
    except ContractError as exc:
        return {"status": "UNKNOWN", "reason": str(exc)}
    receipt_path = output_dir / "independent-verifier-receipt.json"
    write_json(receipt_path, verifier_receipt)
    return {"status": "PASS", "receipt": receipt_path.name, "receipt_sha256": sha256(receipt_path)}


def operation_commands(plan: dict[str, Any], operation: str, env: dict[str, str]) -> tuple[list[tuple[str, list[str], list[str]]], list[str]]:
    binding = plan["operations"][operation]
    if operation == "target_cluster_load":
        return [
            (
                "target-cluster-load",
                ["k6", "run", "--vus", str(binding["vus"]), "--duration", binding["duration"], binding["script"]],
                [],
            )
        ], []
    if operation == "chaos":
        commands: list[tuple[str, list[str], list[str]]] = []
        for case in binding["cases"]:
            prefix = ["kubectl", "--context", binding["context"], "--namespace", binding["namespace"]]
            if case["action"] == "rollout_restart":
                command = prefix + ["rollout", "restart", case["resource"]]
            else:
                command = prefix + ["delete", "pod", "--selector", case["selector"], "--wait=false"]
            commands.append((f"chaos-{case['id']}", command, []))
        return commands, []
    if operation == "redis_loss":
        url = env[binding["redis_url_env"]]
        return [("redis-loss", ["redis-cli", "-u", url, "FLUSHALL", "ASYNC"], [url])], []
    if operation == "production_deployment":
        command = [
            "helm",
            "upgrade",
            "--install",
            binding["release"],
            binding["chart"],
            "--kube-context",
            binding["context"],
            "--namespace",
            binding["namespace"],
            "--atomic",
            "--wait",
            "--timeout",
            binding["timeout"],
            "--set-string",
            f"images.controlPlane={binding['image_digests']['controlPlane']}",
            "--set-string",
            f"images.worker={binding['image_digests']['worker']}",
        ]
        return [("production-deployment", command, [])], []
    return [], [f"{operation} requires its provider-specific repository adapter"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=ROOT / "docs/production-runtime/EXTERNAL-GATE-PLAN.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".elmos/production-runtime/external-gate-report.json")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--operation", choices=("all",) + OPERATIONS, default="all")
    parser.add_argument("--execute", action="store_true", help="perform only the explicitly authorized operations")
    args = parser.parse_args()
    plan_path = resolve_path(args.plan)
    output_path = resolve_path(args.output)
    output_dir = output_path.parent
    run_id = str(uuid.uuid4())
    requested = set(OPERATIONS if args.operation == "all" else (args.operation,))
    try:
        plan = load_object(plan_path)
        validate_plan(plan, ROOT)
        blockers = preflight(plan, ROOT)
        if args.execute:
            if os.environ.get("ELMOS_EXTERNAL_GATE_ACK") != ACK:
                raise ContractError("execution requires ELMOS_EXTERNAL_GATE_ACK with the exact approval phrase")
            if args.authorization is None:
                raise ContractError("execution requires --authorization")
            authorization = load_object(resolve_path(args.authorization))
            validate_authorization(authorization, plan, requested)
            if "production_deployment" in requested and requested != set(OPERATIONS):
                raise ContractError("production deployment requires the complete external gate operation set")
            blockers = {key: value for key, value in blockers.items() if key not in requested and key != "_execution"}
            execution_blockers = preflight(plan, ROOT)
            blockers = {key: value for key, value in execution_blockers.items() if key in requested or key == "_execution"}

        operation_results: dict[str, dict[str, Any]] = {}
        if not args.execute:
            for operation in OPERATIONS:
                operation_results[operation] = {"status": "NOT_RUN", "blockers": blockers.get(operation, ["not requested for execution"])}
            status = "EXTERNAL_GATE_BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE"
        elif blockers:
            for operation in OPERATIONS:
                operation_results[operation] = {"status": "NOT_RUN", "blockers": blockers.get(operation, ["not requested or blocked by another binding"])}
            status = "EXTERNAL_GATE_BLOCKED"
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            for operation in OPERATIONS:
                if operation not in requested:
                    operation_results[operation] = {"status": "NOT_RUN", "blockers": ["operation was not requested"]}
                    continue
                if operation == "independent_verification":
                    # The report is written first so the verifier receives the
                    # exact content-addressed producer output.
                    operation_results[operation] = {"status": "NOT_RUN", "blockers": ["report submission occurs after report materialization"]}
                    continue
                commands, adapter_blockers = operation_commands(plan, operation, os.environ)
                if adapter_blockers:
                    operation_results[operation] = {"status": "NOT_RUN", "blockers": adapter_blockers}
                    continue
                results = [run_binary(output_dir, name, command, secrets) for name, command, secrets in commands]
                operation_results[operation] = {"status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL", "commands": results}
            status = "EXTERNAL_GATE_EXECUTED"

        report = {
            "schema_version": 1,
            "status": status,
            "mode": "EXECUTE" if args.execute else "PLAN_ONLY",
            "test_run_id": run_id,
            "plan_sha256": sha256(plan_path),
            "source_archive_sha256": EXPECTED_PACKAGE_SHA256,
            "package_execution": False,
            "operations": operation_results,
            "external_evidence": {operation: operation_results[operation]["status"] for operation in OPERATIONS},
            "production_certification": "NOT_CERTIFIED",
        }
        write_json(output_path, report)
        if args.execute and not blockers and "independent_verification" in requested:
            result = run_independent_verifier(plan["operations"]["independent_verification"], output_path, output_dir)
            report["operations"]["independent_verification"] = result
            report["external_evidence"]["independent_verification"] = result["status"]
            write_json(output_path, report)
        print(json.dumps({"status": report["status"], "report": str(output_path), "test_run_id": run_id}, sort_keys=True))
        return 0
    except (ContractError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"production-runtime external gate: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
