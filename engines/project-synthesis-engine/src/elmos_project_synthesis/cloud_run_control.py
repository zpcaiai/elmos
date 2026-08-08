#!/usr/bin/env python3
"""Fail-closed Cloud Run plan, deploy, rollback, and cleanup controller.

This module is also emitted verbatim into generated projects. Planning is local;
provider mutations require an exact, expiring authorization record and --execute.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
REGION_RE = re.compile(r"^[a-z]+-[a-z]+[0-9]$")
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
MEMORY_RE = re.compile(r"^[1-9][0-9]*(Mi|Gi)$")
INGRESS = {"internal", "internal-and-cloud-load-balancing"}


class ControlError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ControlError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    project = config.get("project_id")
    region = config.get("region")
    service = config.get("service_name")
    image = config.get("image")
    account = config.get("runtime_service_account")
    if config.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(project, str) or not PROJECT_RE.fullmatch(project):
        errors.append("project_id is invalid")
    elif project.startswith("replace-"):
        errors.append("project_id placeholder must be replaced")
    if not isinstance(region, str) or not REGION_RE.fullmatch(region):
        errors.append("region is invalid")
    if not isinstance(service, str) or not NAME_RE.fullmatch(service):
        errors.append("service_name is invalid")
    release = config.get("release_id")
    if not isinstance(release, str) or not NAME_RE.fullmatch(release) or len(release) > 20:
        errors.append("release_id must be a lowercase Cloud Run suffix of at most 20 characters")
    elif release.startswith("replace-"):
        errors.append("release_id placeholder must be replaced")
    if isinstance(project, str) and isinstance(region, str):
        prefix = f"{region}-docker.pkg.dev/{project}/"
        if not isinstance(image, str) or not image.startswith(prefix) or "@sha256:" not in image:
            errors.append("image must be an Artifact Registry reference in the exact project/region with a digest")
        elif not DIGEST_RE.fullmatch(image.rsplit("@sha256:", 1)[1]):
            errors.append("image digest must contain exactly 64 lowercase hex characters")
        elif image.endswith("@sha256:" + "0" * 64):
            errors.append("image digest placeholder must be replaced")
        suffix = f"@{project}.iam.gserviceaccount.com"
        if not isinstance(account, str) or not account.endswith(suffix):
            errors.append("runtime_service_account must be a service account in the exact project")
        elif account.startswith(("default@", "compute@")) or "-compute@developer.gserviceaccount.com" in account:
            errors.append("default compute identity is forbidden; use a dedicated runtime service account")
    if config.get("ingress") not in INGRESS:
        errors.append("ingress must remain private")
    numeric_ranges = (
        ("port", 1, 65535),
        ("concurrency", 1, 1000),
        ("min_instances", 0, 100),
        ("max_instances", 1, 1000),
    )
    for key, lower, upper in numeric_ranges:
        value = config.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not lower <= value <= upper:
            errors.append(f"{key} must be an integer in [{lower}, {upper}]")
    if isinstance(config.get("min_instances"), int) and isinstance(config.get("max_instances"), int):
        if config["min_instances"] > config["max_instances"]:
            errors.append("min_instances must not exceed max_instances")
    if config.get("cpu") not in {"1", "2", "4", "8"}:
        errors.append("cpu must be one of 1, 2, 4, or 8")
    if not isinstance(config.get("memory"), str) or not MEMORY_RE.fullmatch(config["memory"]):
        errors.append("memory must use an exact Mi or Gi value")
    health = config.get("health")
    if not isinstance(health, dict) or not isinstance(health.get("path"), str) or not health["path"].startswith("/"):
        errors.append("health.path must be an absolute HTTP path")
    secrets = config.get("secrets", [])
    if not isinstance(secrets, list):
        errors.append("secrets must be a list")
    else:
        for index, secret in enumerate(secrets):
            if not isinstance(secret, dict):
                errors.append(f"secrets[{index}] must be an object")
                continue
            if set(secret) != {"mount_path", "name", "version"}:
                errors.append(f"secrets[{index}] may contain only mount_path, name, and version")
                continue
            if not isinstance(secret["mount_path"], str) or not secret["mount_path"].startswith("/run/secrets/"):
                errors.append(f"secrets[{index}].mount_path must be below /run/secrets")
            if not isinstance(secret["name"], str) or not NAME_RE.fullmatch(secret["name"]):
                errors.append(f"secrets[{index}].name is invalid")
            if not isinstance(secret["version"], str) or not secret["version"].isdigit():
                errors.append(f"secrets[{index}].version must be an immutable numeric version")
    return errors


def deploy_command(config: dict[str, Any]) -> list[str]:
    errors = validate_config(config)
    if errors:
        raise ControlError("CONFIG_INVALID:" + "; ".join(errors))
    command = [
        "gcloud", "run", "deploy", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}",
        "--platform=managed", f"--image={config['image']}",
        f"--service-account={config['runtime_service_account']}",
        f"--port={config['port']}", f"--cpu={config['cpu']}", f"--memory={config['memory']}",
        f"--concurrency={config['concurrency']}", f"--min-instances={config['min_instances']}",
        f"--max-instances={config['max_instances']}", f"--ingress={config['ingress']}",
        f"--revision-suffix={config['release_id']}", f"--tag=candidate-{config['release_id']}",
        "--no-allow-unauthenticated", "--no-traffic", "--quiet", "--format=json",
    ]
    secrets = config.get("secrets", [])
    if secrets:
        references = ",".join(
            f"{item['mount_path']}={item['name']}:{item['version']}" for item in secrets
        )
        command.append(f"--set-secrets={references}")
    return command


def plan(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "READY_FOR_AUTHORIZED_EXECUTION",
        "config_digest": _canonical_digest(config),
        "deploy": deploy_command(config),
        "promote": [
            "gcloud", "run", "services", "update-traffic", config["service_name"],
            f"--project={config['project_id']}", f"--region={config['region']}",
            "--to-revisions=DEPLOYED_REVISION=100", "--quiet", "--format=json",
        ],
        "rollback": [
            "gcloud", "run", "services", "update-traffic", config["service_name"],
            f"--project={config['project_id']}", f"--region={config['region']}",
            "--to-revisions=PREVIOUS_REVISION=100", "--quiet", "--format=json",
        ],
        "destroy": [
            "gcloud", "run", "services", "delete", config["service_name"],
            f"--project={config['project_id']}", f"--region={config['region']}", "--quiet",
        ],
        "external_execution_evidence": "NOT_RUN",
    }


def _authorization(path: Path, action: str, config: dict[str, Any], executor: str) -> dict[str, Any]:
    auth = _load(path)
    expected = {
        "schema_version": 1,
        "approved": True,
        "action": action,
        "config_digest": _canonical_digest(config),
        "project_id": config["project_id"],
        "region": config["region"],
        "service_name": config["service_name"],
    }
    for key, value in expected.items():
        if auth.get(key) != value:
            raise ControlError(f"AUTHORIZATION_SCOPE_MISMATCH:{key}")
    approver = auth.get("approver")
    if not isinstance(approver, str) or not approver or approver == executor:
        raise ControlError("AUTHORIZATION_REQUIRES_SEPARATE_APPROVER")
    try:
        expires = dt.datetime.fromisoformat(str(auth["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ControlError("AUTHORIZATION_EXPIRY_INVALID") from exc
    if expires <= dt.datetime.now(dt.UTC):
        raise ControlError("AUTHORIZATION_EXPIRED")
    return auth


def _run(command: list[str]) -> dict[str, Any]:
    if not command or Path(command[0]).name != "gcloud":
        raise ControlError("ONLY_GCLOUD_COMMANDS_ARE_ALLOWED")
    executable = shutil.which(command[0])
    if not executable:
        raise ControlError("GCLOUD_NOT_INSTALLED")
    completed = subprocess.run(  # noqa: S603 - executable and arguments are validated, never passed to a shell.
        [executable, *command[1:]], check=False, capture_output=True, text=True
    )
    if completed.returncode:
        message = completed.stderr.strip().splitlines()[-1:] or ["provider command failed"]
        raise ControlError(f"GCLOUD_FAILED:{command[1]}:{message[0]}")
    if not completed.stdout.strip():
        return {}
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ControlError("GCLOUD_JSON_OUTPUT_REQUIRED") from exc
    return value if isinstance(value, dict) else {"result": value}


def _describe(config: dict[str, Any]) -> dict[str, Any]:
    return _run([
        "gcloud", "run", "services", "describe", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}", "--format=json",
    ])


def candidate_probe_endpoints(service: dict[str, Any], tag: str) -> tuple[str, str]:
    status = service.get("status", {})
    audience = status.get("url")
    traffic = status.get("traffic", [])
    endpoint = next((item.get("uri") for item in traffic if item.get("tag") == tag), None)
    for label, value in (("SERVICE_AUDIENCE", audience), ("CANDIDATE_TAG_URI", endpoint)):
        if not isinstance(value, str):
            raise ControlError(f"{label}_NOT_OBSERVED")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".run.app"):
            raise ControlError(f"{label}_INVALID")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ControlError(f"{label}_INVALID")
    assert isinstance(endpoint, str)
    assert isinstance(audience, str)
    return endpoint, audience


def preflight(config: dict[str, Any]) -> dict[str, Any]:
    errors = validate_config(config)
    if errors:
        raise ControlError("CONFIG_INVALID:" + "; ".join(errors))
    executable = shutil.which("gcloud")
    if not executable:
        raise ControlError("GCLOUD_NOT_INSTALLED")
    version = _run([executable, "version", "--format=json"])
    account = _run([executable, "auth", "list", "--filter=status:ACTIVE", "--format=json"])
    if not account.get("result", account):
        raise ControlError("GCLOUD_ACTIVE_ACCOUNT_REQUIRED")
    return {"status": "PASSED", "gcloud": version, "config_digest": _canonical_digest(config)}


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


def execute_deploy(config: dict[str, Any], authorization: Path, executor: str, receipt_path: Path) -> None:
    preflight(config)
    auth = _authorization(authorization, "deploy", config, executor)
    try:
        before = _describe(config)
        previous = before.get("status", {}).get("latestReadyRevisionName")
    except ControlError:
        previous = None
    _run(deploy_command(config))
    after = _describe(config)
    revision = after.get("status", {}).get("latestReadyRevisionName")
    if not isinstance(revision, str) or revision == previous:
        raise ControlError("NEW_READY_REVISION_NOT_OBSERVED")
    tag = f"candidate-{config['release_id']}"
    uri, audience = candidate_probe_endpoints(after, tag)
    executable = shutil.which("gcloud")
    if not executable:
        raise ControlError("GCLOUD_NOT_INSTALLED")
    token_result = subprocess.run(  # noqa: S603 - fixed gcloud operation with provider-derived HTTPS audience.
        [executable, "auth", "print-identity-token", f"--audiences={audience}"],
        check=False, capture_output=True, text=True,
    )
    token = token_result.stdout.strip()
    if token_result.returncode or not token:
        raise ControlError("IDENTITY_TOKEN_REQUIRED_FOR_PRIVATE_HEALTH_PROBE")
    request = urllib.request.Request(  # noqa: S310 - URI is verified provider-derived HTTPS.
        uri.rstrip("/") + config["health"]["path"]
    )
    request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - URI is provider-derived HTTPS.
        body = json.loads(response.read().decode("utf-8"))
    expected = config["health"].get("expected_json", {"status": "UP"})
    if any(body.get(key) != value for key, value in expected.items()):
        raise ControlError("PRIVATE_HEALTH_CONTRACT_FAILED")
    promote = [
        "gcloud", "run", "services", "update-traffic", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}",
        f"--to-revisions={revision}=100", "--quiet", "--format=json",
    ]
    _run(promote)
    _write_receipt(receipt_path, {
        "schema_version": 1, "action": "deploy", "status": "passed",
        "executed_at": dt.datetime.now(dt.UTC).isoformat(), "executor": executor,
        "approver": auth["approver"], "config_digest": _canonical_digest(config),
        "image": config["image"], "previous_revision": previous, "deployed_revision": revision,
        "private_health_probe": "passed", "traffic": {revision: 100},
        "certification_effect": "NONE_REQUIRES_INDEPENDENT_GATE",
    })


def execute_rollback(
    config: dict[str, Any],
    authorization: Path,
    executor: str,
    receipt_path: Path,
    deploy_receipt: Path,
) -> None:
    preflight(config)
    auth = _authorization(authorization, "rollback", config, executor)
    prior = _load(deploy_receipt)
    if prior.get("config_digest") != _canonical_digest(config) or prior.get("status") != "passed":
        raise ControlError("DEPLOY_RECEIPT_SCOPE_MISMATCH")
    revision = prior.get("previous_revision")
    if not isinstance(revision, str) or not NAME_RE.fullmatch(revision):
        raise ControlError("PREVIOUS_REVISION_REQUIRED")
    _run([
        "gcloud", "run", "services", "update-traffic", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}",
        f"--to-revisions={revision}=100", "--quiet", "--format=json",
    ])
    _write_receipt(receipt_path, {
        "schema_version": 1, "action": "rollback", "status": "passed",
        "executed_at": dt.datetime.now(dt.UTC).isoformat(), "executor": executor,
        "approver": auth["approver"], "config_digest": _canonical_digest(config),
        "restored_revision": revision, "certification_effect": "NONE_REQUIRES_INDEPENDENT_GATE",
    })


def execute_destroy(config: dict[str, Any], authorization: Path, executor: str, receipt_path: Path) -> None:
    preflight(config)
    auth = _authorization(authorization, "destroy", config, executor)
    _run([
        "gcloud", "run", "services", "delete", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}", "--quiet", "--format=json",
    ])
    _write_receipt(receipt_path, {
        "schema_version": 1, "action": "destroy", "status": "passed",
        "executed_at": dt.datetime.now(dt.UTC).isoformat(), "executor": executor,
        "approver": auth["approver"], "config_digest": _canonical_digest(config),
        "service_deleted": True, "orphan_and_billing_review": "REQUIRED",
        "certification_effect": "NONE_REQUIRES_INDEPENDENT_GATE",
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("validate", "plan", "preflight", "deploy", "rollback", "destroy"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--executor")
    parser.add_argument("--receipt", type=Path, default=Path("deploy/evidence/cloud-run-receipt.json"))
    parser.add_argument("--deploy-receipt", type=Path)
    args = parser.parse_args()
    try:
        config = _load(args.config)
        if args.action == "validate":
            errors = validate_config(config)
            if errors:
                raise ControlError("CONFIG_INVALID:" + "; ".join(errors))
            output = {"status": "PASSED", "config_digest": _canonical_digest(config)}
        elif args.action == "plan":
            output = plan(config)
        elif args.action == "preflight":
            output = preflight(config)
        else:
            if not args.execute or not args.authorization or not args.executor:
                raise ControlError("MUTATION_REQUIRES_EXECUTE_AUTHORIZATION_AND_EXECUTOR")
            if args.action == "deploy":
                execute_deploy(config, args.authorization, args.executor, args.receipt)
            elif args.action == "rollback":
                if not args.deploy_receipt:
                    raise ControlError("ROLLBACK_REQUIRES_DEPLOY_RECEIPT")
                execute_rollback(config, args.authorization, args.executor, args.receipt, args.deploy_receipt)
            else:
                execute_destroy(config, args.authorization, args.executor, args.receipt)
            output = _load(args.receipt)
        print(json.dumps(output, indent=2))
        return 0
    except (ControlError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
