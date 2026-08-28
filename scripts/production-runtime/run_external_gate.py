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
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from external_provider_adapter import execute_provider_probe
from hosted_pitr_adapter import (
    cleanup_command,
    describe_command,
    restore_command,
    restored_endpoint,
    wait_command,
)

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


def run_binary(
    output_dir: Path,
    name: str,
    command: list[str],
    secrets: list[str] | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    command_environment = os.environ.copy()
    if environment:
        command_environment.update(environment)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=command_environment,
        text=True,
        capture_output=True,
        check=False,
    )
    log = command_log(output_dir, name, command, result, secrets or [])
    evidence = {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "log": log,
        "log_sha256": sha256(output_dir / log),
    }
    # Private in-process values are removed before report serialization.
    evidence["_stdout"] = result.stdout
    return evidence


def public_evidence(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if not key.startswith("_")}


def gate_probe(
    plan: dict[str, Any],
    output_dir: Path,
    name: str,
    path: str = "/internal/v1/production-runtime/gate/invariants",
    expect_disabled: bool = False,
) -> dict[str, Any]:
    binding = plan["operations"]["target_cluster_load"]
    base_url = os.environ[binding["scheduler_base_url_env"]].rstrip("/")
    token = os.environ[binding["gate_token_env"]]
    request = urllib.request.Request(base_url + path, method="GET")
    request.add_header("Accept", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    status_code = 0
    body = b""
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read(1024 * 1024)
    except Exception as exc:
        result = {
            "status": "UNKNOWN",
            "reason": f"gate probe transport is uncertain: {type(exc).__name__}",
        }
        log = output_dir / f"{name}.json"
        write_json(log, result)
        return {**result, "log": log.name, "log_sha256": sha256(log)}
    if expect_disabled:
        passed = status_code in {404, 410}
        result = {"status": "PASS" if passed else "FAIL", "http_status": status_code}
    else:
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        passed = status_code == 200 and parsed.get("status") == "PASS" \
            and parsed.get("violations") == []
        result = {
            "status": "PASS" if passed else "FAIL",
            "http_status": status_code,
            "response_status": parsed.get("status", "INVALID"),
            "violations": parsed.get("violations", ["INVALID_GATE_RESPONSE"]),
        }
    log = output_dir / f"{name}.json"
    write_json(log, result)
    return {**result, "log": log.name, "log_sha256": sha256(log)}


def postgres_environment(database_url: str) -> dict[str, str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ContractError("PITR source database URL must be a PostgreSQL URL")
    if parsed.path in {"", "/"}:
        raise ContractError("PITR source database URL must name a database")
    environment = {
        "PGHOST": parsed.hostname,
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": unquote(parsed.path.lstrip("/")),
        "PGSSLMODE": "verify-full",
    }
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return environment


def execute_hosted_pitr(
    plan: dict[str, Any], output_dir: Path, environ: dict[str, str]
) -> dict[str, Any]:
    binding = plan["operations"]["backup_pitr"]
    change_id = plan["execution"]["change_id"]
    marker_args = [
        "--set", f"tenant_id={binding['marker_tenant_id']}",
        "--set", f"marker_id={binding['marker_id']}",
        "--set", f"marker_sha256={binding['marker_sha256']}",
        "--set", f"change_id={change_id}",
    ]
    source_url = environ[binding["source_database_url_env"]]
    source_env = postgres_environment(source_url)
    source_root_cert = environ.get(binding.get("restore_ssl_root_cert_env", ""), "")
    if source_root_cert:
        source_env["PGSSLROOTCERT"] = source_root_cert
    marker = run_binary(
        output_dir,
        "pitr-source-marker",
        ["psql", "--no-psqlrc", "--no-align", "--tuples-only", *marker_args,
         "--file", "scripts/production-runtime/prepare_pitr_marker.sql"],
        [source_url, source_env.get("PGPASSWORD", "")],
        source_env,
    )
    commands = [public_evidence(marker)]
    if marker["status"] != "PASS":
        return {"status": "FAIL", "phase": "SOURCE_MARKER", "commands": commands}
    timestamp_lines = [line.strip() for line in marker["_stdout"].splitlines() if "T" in line and line.strip().endswith("Z")]
    if not timestamp_lines:
        return {"status": "UNKNOWN", "phase": "SOURCE_MARKER_TIME", "commands": commands}
    marker_time = datetime.fromisoformat(timestamp_lines[-1].replace("Z", "+00:00"))
    restore_time = (marker_time + timedelta(seconds=2)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    time.sleep(binding["archive_delay_seconds"])
    restored = False
    cleanup_result: dict[str, Any] | None = None
    outcome: dict[str, Any]
    try:
        restore = run_binary(output_dir, "pitr-restore", restore_command(binding, restore_time))
        commands.append(public_evidence(restore))
        if restore["status"] != "PASS":
            return {"status": "FAIL", "phase": "RESTORE_REQUEST", "restore_time": restore_time, "commands": commands}
        restored = True
        wait = wait_command(binding)
        if wait:
            wait_result = run_binary(output_dir, "pitr-wait", wait)
            commands.append(public_evidence(wait_result))
            if wait_result["status"] != "PASS":
                return {"status": "UNKNOWN", "phase": "RESTORE_WAIT", "restore_time": restore_time, "commands": commands}
        describe = run_binary(output_dir, "pitr-describe", describe_command(binding))
        commands.append(public_evidence(describe))
        if describe["status"] != "PASS":
            return {"status": "UNKNOWN", "phase": "RESTORE_DESCRIBE", "restore_time": restore_time, "commands": commands}
        host, port = restored_endpoint(binding, describe["_stdout"])
        username = environ[binding["restore_username_env"]]
        password = environ[binding["restore_password_env"]]
        target_env = {
            "PGHOST": host,
            "PGPORT": str(port),
            "PGDATABASE": binding["restore_database"],
            "PGUSER": username,
            "PGPASSWORD": password,
            "PGSSLMODE": "verify-full",
        }
        if source_root_cert:
            target_env["PGSSLROOTCERT"] = source_root_cert
        verification = run_binary(
            output_dir,
            "pitr-verify",
            ["psql", "--no-psqlrc", "--no-align", "--tuples-only", *marker_args,
             "--file", "scripts/production-runtime/verify_pitr_restore.sql"],
            [password],
            target_env,
        )
        commands.append(public_evidence(verification))
        outcome = {
            "status": "PASS" if verification["status"] == "PASS" else "FAIL",
            "phase": "VERIFIED" if verification["status"] == "PASS" else "RESTORE_INVARIANTS",
            "driver": binding["driver"],
            "restore_target": binding["restore_target"],
            "restore_time": restore_time,
            "endpoint_sha256": hashlib.sha256(f"{host}:{port}".encode()).hexdigest(),
            "commands": commands,
        }
    finally:
        if restored and binding["cleanup_after_verification"]:
            cleanup_result = run_binary(output_dir, "pitr-cleanup", cleanup_command(binding))
            commands.append(public_evidence(cleanup_result))
    if cleanup_result and cleanup_result["status"] != "PASS":
        outcome["status"] = "UNKNOWN"
        outcome["phase"] = "CLEANUP_UNCERTAIN"
    return outcome


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
    request.add_header("X-ELMOS-Producer-Actor", operation["producer_actor"])
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


def kubectl_prefix(binding: dict[str, Any]) -> list[str]:
    return [
        "kubectl", "--context", binding["context"],
        "--namespace", binding["namespace"],
    ]


def execute_chaos(plan: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    binding = plan["operations"]["chaos"]
    evidence: list[dict[str, Any]] = []
    for case in binding["cases"]:
        before = gate_probe(plan, output_dir, f"chaos-{case['id']}-before")
        evidence.append(before)
        if before["status"] != "PASS":
            return {"status": "FAIL", "phase": "PRE_INVARIANTS", "evidence": evidence}
        prefix = kubectl_prefix(binding)
        if case["action"] == "rollout_restart":
            action = prefix + ["rollout", "restart", case["resource"]]
        else:
            action = prefix + ["delete", "pod", "--selector", case["selector"], "--wait=false"]
        action_result = public_evidence(run_binary(
            output_dir, f"chaos-{case['id']}-action", action))
        evidence.append(action_result)
        if action_result["status"] != "PASS":
            return {"status": "FAIL", "phase": "CHAOS_ACTION", "evidence": evidence}
        recovery = public_evidence(run_binary(
            output_dir,
            f"chaos-{case['id']}-recovery",
            prefix + ["rollout", "status", case["recovery_resource"], "--timeout=10m"],
        ))
        evidence.append(recovery)
        if recovery["status"] != "PASS":
            return {"status": "UNKNOWN", "phase": "RECOVERY_WAIT", "evidence": evidence}
        after = gate_probe(plan, output_dir, f"chaos-{case['id']}-after")
        evidence.append(after)
        if after["status"] != "PASS":
            return {"status": "FAIL", "phase": "POST_INVARIANTS", "evidence": evidence}
    return {"status": "PASS", "evidence": evidence}


def execute_worker_kill(plan: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    binding = plan["operations"]["worker_process_kill"]
    evidence: list[dict[str, Any]] = []
    before = gate_probe(plan, output_dir, "worker-kill-before")
    evidence.append(before)
    if before["status"] != "PASS":
        return {"status": "FAIL", "phase": "PRE_INVARIANTS", "evidence": evidence}
    prefix = kubectl_prefix(binding)
    listing = run_binary(
        output_dir, "worker-kill-list",
        prefix + ["get", "pods", "--selector", binding["selector"], "-o", "json"],
    )
    evidence.append(public_evidence(listing))
    if listing["status"] != "PASS":
        return {"status": "FAIL", "phase": "WORKER_DISCOVERY", "evidence": evidence}
    try:
        pods = json.loads(listing["_stdout"])["items"]
        ready = sorted(
            (
                item for item in pods
                if item.get("metadata", {}).get("deletionTimestamp") is None
                and all(status.get("ready") for status in item.get("status", {}).get("containerStatuses", []))
                and item.get("status", {}).get("containerStatuses")
            ),
            key=lambda item: item["metadata"]["name"],
        )
        if len(ready) < binding["minimum_ready_replicas"]:
            raise ValueError("insufficient ready workers")
        victim = ready[0]["metadata"]["name"]
        victim_uid = ready[0]["metadata"]["uid"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "phase": "WORKER_SELECTION", "reason": str(exc), "evidence": evidence}
    killed = public_evidence(run_binary(
        output_dir, "worker-kill-action",
        prefix + ["delete", "pod", victim, "--wait=false"],
    ))
    killed["victim_uid_sha256"] = hashlib.sha256(victim_uid.encode()).hexdigest()
    evidence.append(killed)
    if killed["status"] != "PASS":
        return {"status": "FAIL", "phase": "WORKER_KILL", "evidence": evidence}
    recovery = public_evidence(run_binary(
        output_dir, "worker-kill-recovery",
        prefix + ["rollout", "status", binding["recovery_resource"], "--timeout=10m"],
    ))
    evidence.append(recovery)
    if recovery["status"] != "PASS":
        return {"status": "UNKNOWN", "phase": "WORKER_RECOVERY", "evidence": evidence}
    after = gate_probe(plan, output_dir, "worker-kill-after")
    evidence.append(after)
    return {
        "status": "PASS" if after["status"] == "PASS" else "FAIL",
        "phase": "VERIFIED" if after["status"] == "PASS" else "POST_INVARIANTS",
        "evidence": evidence,
    }


def execute_redis_loss(plan: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    binding = plan["operations"]["redis_loss"]
    redis_url = os.environ[binding["redis_url_env"]]
    evidence: list[dict[str, Any]] = []
    before = gate_probe(plan, output_dir, "redis-loss-before")
    evidence.append(before)
    if before["status"] != "PASS":
        return {"status": "FAIL", "phase": "PRE_INVARIANTS", "evidence": evidence}
    sentinel_key = f"elmos:gate:{uuid.uuid4()}"
    sentinel_value = uuid.uuid4().hex
    create = run_binary(
        output_dir, "redis-loss-sentinel-create",
        ["redis-cli", "--no-auth-warning", "-u", redis_url,
         "SET", sentinel_key, sentinel_value, "EX", "300", "NX"],
        [redis_url, sentinel_value],
    )
    evidence.append(public_evidence(create))
    if create["status"] != "PASS" or create["_stdout"].strip() != "OK":
        return {"status": "FAIL", "phase": "SENTINEL_CREATE", "evidence": evidence}
    flush = run_binary(
        output_dir, "redis-loss-flushdb",
        ["redis-cli", "--no-auth-warning", "-u", redis_url, "FLUSHDB", "ASYNC"],
        [redis_url],
    )
    evidence.append(public_evidence(flush))
    if flush["status"] != "PASS" or flush["_stdout"].strip() != "OK":
        return {"status": "FAIL", "phase": "FLUSHDB", "evidence": evidence}
    absent = False
    for attempt in range(20):
        check_result = run_binary(
            output_dir, f"redis-loss-sentinel-check-{attempt:02d}",
            ["redis-cli", "--no-auth-warning", "-u", redis_url, "EXISTS", sentinel_key],
            [redis_url],
        )
        evidence.append(public_evidence(check_result))
        if check_result["status"] == "PASS" and check_result["_stdout"].strip() == "0":
            absent = True
            break
        time.sleep(1)
    if not absent:
        return {"status": "UNKNOWN", "phase": "ASYNC_FLUSH_CONFIRMATION", "evidence": evidence}
    after = gate_probe(plan, output_dir, "redis-loss-after")
    evidence.append(after)
    return {
        "status": "PASS" if after["status"] == "PASS" else "FAIL",
        "phase": "VERIFIED" if after["status"] == "PASS" else "POST_INVARIANTS",
        "resource_id": binding["resource_id"],
        "evidence": evidence,
    }


def execute_deployment(
    plan: dict[str, Any], output_dir: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = plan["operations"]["production_deployment"]
    values_path = os.environ[binding["values_file_env"]]
    monitoring = verify_monitoring_crds(binding, output_dir)
    if monitoring["status"] != "PASS":
        return (
            {"status": monitoring["status"], "phase": "MONITORING_CRDS", "evidence": monitoring["evidence"]},
            {"deployed": False},
        )
    supply_chain = verify_image_supply_chain(binding, output_dir)
    if supply_chain["status"] != "PASS":
        return (
            {"status": supply_chain["status"], "phase": "SUPPLY_CHAIN", "evidence": monitoring["evidence"] + supply_chain["evidence"]},
            {"deployed": False},
        )
    candidate_values = helm_candidate_value_arguments(binding, values_path)
    rendered = run_binary(
        output_dir,
        "production-deployment-render",
        [
            "helm", "template", binding["release"], binding["chart"],
            "--namespace", binding["namespace"],
            *candidate_values,
        ],
        [values_path],
    )
    if rendered["status"] != "PASS":
        return (
        {
            "status": "FAIL",
            "phase": "HELM_RENDER",
            "evidence": monitoring["evidence"] + supply_chain["evidence"] + [public_evidence(rendered)],
            },
            {"deployed": False},
        )
    prefix = [
        "helm", "--kube-context", binding["context"],
        "--namespace", binding["namespace"],
    ]
    status = run_binary(
        output_dir, "production-deployment-prior-status",
        prefix + ["list", "--all", "--filter", f"^{binding['release']}$", "--output", "json"],
    )
    prior_revision: int | None = None
    if status["status"] != "PASS":
        return (
            {"status": "UNKNOWN", "phase": "PRIOR_RELEASE_STATE",
             "evidence": [public_evidence(rendered), public_evidence(status)]},
            {"deployed": False},
        )
    try:
        releases = json.loads(status["_stdout"])
        if not isinstance(releases, list) or len(releases) > 1:
            raise ValueError("ambiguous Helm release inventory")
        if releases:
            prior_revision = int(releases[0]["revision"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return (
            {"status": "UNKNOWN", "phase": "PRIOR_RELEASE_STATE",
             "reason": str(exc),
             "evidence": [public_evidence(rendered), public_evidence(status)]},
            {"deployed": False},
        )
    command = [
        "helm", "upgrade", "--install", binding["release"], binding["chart"],
        "--kube-context", binding["context"],
        "--namespace", binding["namespace"],
        "--atomic", "--wait", "--timeout", binding["timeout"],
        "--history-max", "20",
        *candidate_values,
    ]
    deployed = run_binary(output_dir, "production-deployment", command, [values_path])
    evidence = [
        *monitoring["evidence"], *supply_chain["evidence"], public_evidence(rendered),
        public_evidence(status), public_evidence(deployed)
    ]
    state = {
        "deployed": deployed["status"] == "PASS",
        "prior_revision": prior_revision,
        "binding": binding,
    }
    if deployed["status"] != "PASS":
        return {"status": "FAIL", "phase": "HELM_UPGRADE", "evidence": evidence}, state
    resource_prefix = binding["resource_prefix"]
    for resource in (
        f"deployment/{resource_prefix}-scheduler",
        f"deployment/{resource_prefix}-billing",
        f"deployment/{resource_prefix}-projector",
        f"statefulset/{resource_prefix}-worker",
    ):
        safe_name = resource.replace("/", "-")
        rollout = public_evidence(run_binary(
            output_dir, f"production-deployment-{safe_name}",
            ["kubectl", "--context", binding["context"], "--namespace", binding["namespace"],
             "rollout", "status", resource, "--timeout", binding["timeout"]],
        ))
        evidence.append(rollout)
        if rollout["status"] != "PASS":
            return {"status": "UNKNOWN", "phase": "ROLLOUT_READINESS", "evidence": evidence}, state
    return {"status": "PASS", "phase": "VALIDATION_GATE_ENABLED", "evidence": evidence}, state


def verify_monitoring_crds(binding: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Require the exact Prometheus Operator APIs before chart mutation."""
    result = public_evidence(run_binary(
        output_dir,
        "production-deployment-monitoring-crds",
        monitoring_crd_command(binding),
    ))
    return {"status": result["status"], "evidence": [result]}


def monitoring_crd_command(binding: dict[str, Any]) -> list[str]:
    """Build the read-only CRD prerequisite probe for the exact cluster context."""
    context = binding["context"]
    return [
        "kubectl", "--context", context, "get", "crd",
        "podmonitors.monitoring.coreos.com",
        "prometheusrules.monitoring.coreos.com", "-o", "name",
    ]


def supply_chain_commands(binding: dict[str, Any], signing_key: str) -> list[tuple[str, list[str]]]:
    """Return fixed cosign commands for the exact digest-pinned release images."""
    contract = binding["supply_chain"]
    commands: list[tuple[str, list[str]]] = []
    for image_name, image in binding["image_digests"].items():
        commands.extend([
            (
                f"supply-chain-{image_name}-signature",
                ["cosign", "verify", "--key", signing_key, "--output", "json", image],
            ),
            (
                f"supply-chain-{image_name}-sbom",
                ["cosign", "verify-attestation", "--key", signing_key,
                 "--type", contract["sbom_predicate_type"], "--output", "json", image],
            ),
            (
                f"supply-chain-{image_name}-provenance",
                ["cosign", "verify-attestation", "--key", signing_key,
                 "--type", contract["provenance_predicate_type"], "--output", "json", image],
            ),
        ])
    return commands


def verify_image_supply_chain(binding: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    contract = binding["supply_chain"]
    signing_key = os.environ[contract["signing_key_env"]]
    evidence: list[dict[str, Any]] = []
    for name, command in supply_chain_commands(binding, signing_key):
        result = public_evidence(run_binary(output_dir, name, command, [signing_key]))
        evidence.append(result)
        if result["status"] != "PASS":
            return {"status": "FAIL", "evidence": evidence}
    return {"status": "PASS", "evidence": evidence}


def helm_candidate_value_arguments(binding: dict[str, Any], values_path: str) -> list[str]:
    """Return the exact shared values for render and mutation commands."""
    return [
        "--values", values_path,
        "--set-string", f"fullnameOverride={binding['resource_prefix']}",
        "--set-string", f"images.controlPlane={binding['image_digests']['controlPlane']}",
        "--set-string", f"images.worker={binding['image_digests']['worker']}",
        "--set", "gate.enabled=true",
        "--set", "validation.enforceProductionValues=true",
    ]


def rollback_deployment(state: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    if not state.get("deployed"):
        return {"status": "NOT_RUN", "reason": "candidate deployment was not committed"}
    binding = state["binding"]
    if state.get("prior_revision") is None:
        command = [
            "helm", "uninstall", binding["release"],
            "--kube-context", binding["context"],
            "--namespace", binding["namespace"],
            "--wait", "--timeout", binding["timeout"],
        ]
    else:
        command = [
            "helm", "rollback", binding["release"], str(state["prior_revision"]),
            "--kube-context", binding["context"],
            "--namespace", binding["namespace"],
            "--wait", "--timeout", binding["timeout"],
        ]
    return public_evidence(run_binary(output_dir, "production-deployment-rollback", command))


def disable_validation_gate(
    plan: dict[str, Any], output_dir: Path
) -> dict[str, Any]:
    binding = plan["operations"]["production_deployment"]
    command = [
        "helm", "upgrade", binding["release"], binding["chart"],
        "--kube-context", binding["context"],
        "--namespace", binding["namespace"],
        "--reuse-values", "--set", "gate.enabled=false",
        "--atomic", "--wait", "--timeout", binding["timeout"],
    ]
    result = public_evidence(run_binary(
        output_dir, "production-deployment-disable-gate", command))
    if result["status"] != "PASS":
        return {"status": "UNKNOWN", "phase": "GATE_DISABLE", "evidence": [result]}
    disabled = gate_probe(
        plan, output_dir, "production-deployment-gate-disabled",
        expect_disabled=True)
    return {
        "status": "PASS" if disabled["status"] == "PASS" else "UNKNOWN",
        "phase": "GATE_DISABLED" if disabled["status"] == "PASS" else "GATE_DISABLE_VERIFICATION",
        "evidence": [result, disabled],
    }


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
    return [], [f"{operation} is implemented by a typed in-process adapter"]


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
                operation_results[operation] = (
                    {"status": "NOT_RUN", "blockers": ["operation was not requested"]}
                    if operation not in requested else
                    {"status": "NOT_RUN", "blockers": ["operation is pending execution"]}
                )
            deployment_state: dict[str, Any] | None = None
            execution_order = (
                "production_deployment", "provider_runtime", "target_cluster_load",
                "chaos", "worker_process_kill", "redis_loss", "backup_pitr",
            )
            for operation in execution_order:
                if operation not in requested:
                    continue
                if deployment_state is not None \
                        and operation != "production_deployment" \
                        and operation_results["production_deployment"]["status"] != "PASS":
                    operation_results[operation] = {
                        "status": "NOT_RUN",
                        "blockers": ["candidate deployment did not become ready"],
                    }
                    continue
                if operation == "production_deployment":
                    result, deployment_state = execute_deployment(plan, output_dir)
                    operation_results[operation] = result
                    continue
                if operation == "provider_runtime":
                    operation_results[operation] = execute_provider_probe(
                        plan["operations"][operation], output_dir, os.environ)
                    continue
                if operation == "target_cluster_load":
                    binding = plan["operations"][operation]
                    result = public_evidence(run_binary(
                        output_dir,
                        "target-cluster-load",
                        ["k6", "run", "--vus", str(binding["vus"]),
                         "--duration", binding["duration"], binding["script"]],
                        environment={"ELMOS_GATE_RUN_ID": run_id},
                    ))
                    operation_results[operation] = {
                        "status": result["status"], "commands": [result]}
                    continue
                if operation == "chaos":
                    operation_results[operation] = execute_chaos(plan, output_dir)
                    continue
                if operation == "worker_process_kill":
                    operation_results[operation] = execute_worker_kill(plan, output_dir)
                    continue
                if operation == "redis_loss":
                    operation_results[operation] = execute_redis_loss(plan, output_dir)
                    continue
                if operation == "backup_pitr":
                    operation_results[operation] = execute_hosted_pitr(
                        plan, output_dir, os.environ)
                    continue
            if "independent_verification" in requested:
                operation_results["independent_verification"] = {
                    "status": "NOT_RUN",
                    "blockers": ["producer report has not yet been independently verified"],
                }

            non_independent = requested - {"independent_verification"}
            failed_before_verifier = any(
                operation_results[name]["status"] != "PASS"
                for name in non_independent
            )
            if deployment_state and deployment_state.get("deployed"):
                if failed_before_verifier:
                    rollback = rollback_deployment(deployment_state, output_dir)
                    deployment = operation_results["production_deployment"]
                    deployment.setdefault("evidence", []).append(rollback)
                    deployment["status"] = "FAIL" if rollback["status"] == "PASS" else "UNKNOWN"
                    deployment["phase"] = "ROLLED_BACK_AFTER_GATE_FAILURE" \
                        if rollback["status"] == "PASS" else "ROLLBACK_UNCERTAIN"
                else:
                    hardened = disable_validation_gate(plan, output_dir)
                    deployment = operation_results["production_deployment"]
                    deployment.setdefault("evidence", []).extend(hardened.get("evidence", []))
                    deployment["status"] = hardened["status"]
                    deployment["phase"] = hardened["phase"]
                    if hardened["status"] != "PASS":
                        rollback = rollback_deployment(deployment_state, output_dir)
                        deployment.setdefault("evidence", []).append(rollback)
                        deployment["status"] = "UNKNOWN"
                        deployment["phase"] = "POST_VALIDATION_HARDENING_OR_ROLLBACK_UNCERTAIN"
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
        if args.execute and not blockers and "independent_verification" in requested:
            reviewable = requested - {"independent_verification"}
            if all(report["operations"][name]["status"] == "PASS" for name in reviewable):
                producer_path = output_dir / "external-gate-producer-report.json"
                report["status"] = "AWAITING_INDEPENDENT_VERIFICATION"
                write_json(producer_path, report)
                result = run_independent_verifier(
                    plan["operations"]["independent_verification"],
                    producer_path, output_dir)
                report["operations"]["independent_verification"] = result
                report["external_evidence"]["independent_verification"] = result["status"]
                report["independent_input_report"] = {
                    "path": producer_path.name,
                    "sha256": sha256(producer_path),
                }
                if result["status"] != "PASS" and 'deployment_state' in locals() \
                        and deployment_state and deployment_state.get("deployed"):
                    rollback = rollback_deployment(deployment_state, output_dir)
                    deployment = report["operations"]["production_deployment"]
                    deployment.setdefault("evidence", []).append(rollback)
                    deployment["status"] = "FAIL" if rollback["status"] == "PASS" else "UNKNOWN"
                    deployment["phase"] = "ROLLED_BACK_AFTER_VERIFIER_FAILURE" \
                        if rollback["status"] == "PASS" else "ROLLBACK_UNCERTAIN"
                    report["external_evidence"]["production_deployment"] = deployment["status"]
        if args.execute and not blockers:
            requested_statuses = [report["operations"][name]["status"] for name in requested]
            if all(value == "PASS" for value in requested_statuses):
                report["status"] = "EXTERNAL_GATE_PASS"
            elif any(value == "FAIL" for value in requested_statuses):
                report["status"] = "EXTERNAL_GATE_FAIL"
            elif any(value == "UNKNOWN" for value in requested_statuses):
                report["status"] = "EXTERNAL_GATE_UNKNOWN"
            else:
                report["status"] = "EXTERNAL_GATE_INCOMPLETE"
        write_json(output_path, report)
        print(json.dumps({"status": report["status"], "report": str(output_path), "test_run_id": run_id}, sort_keys=True))
        if args.execute and not blockers:
            return 0 if all(report["operations"][name]["status"] == "PASS" for name in requested) else 2
        return 0
    except (ContractError, OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"production-runtime external gate: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
