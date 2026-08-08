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
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
REGION_RE = re.compile(r"^[a-z]+-[a-z]+[0-9]$")
DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
MEMORY_RE = re.compile(r"^[1-9][0-9]*(Mi|Gi)$")
ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9._:/@+-]{1,512}$")
HEALTH_PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+;=:@%/-]{0,255}$")
INGRESS = {"internal", "internal-and-cloud-load-balancing"}
MAX_JSON_BYTES = 1_048_576
MAX_HEALTH_BYTES = 65_536
MAX_IDENTITY_TOKEN_BYTES = 16_384
MAX_AUTHORIZATION_LIFETIME = dt.timedelta(hours=24)
PROVIDER_COMMAND_TIMEOUT_SECONDS = 900
ALLOWED_CONFIG_KEYS = {
    "schema_version",
    "project_id",
    "region",
    "service_name",
    "release_id",
    "image",
    "runtime_service_account",
    "port",
    "cpu",
    "memory",
    "concurrency",
    "min_instances",
    "max_instances",
    "timeout_seconds",
    "ingress",
    "health",
    "secrets",
    "environment",
}


class ControlError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ControlError(f"JSON_FILE_UNSAFE:{path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ControlError(f"JSON_FILE_TOO_LARGE:{path}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant)
    if not isinstance(value, dict):
        raise ControlError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown_keys = sorted(set(config) - ALLOWED_CONFIG_KEYS)
    if unknown_keys:
        errors.append("unknown configuration keys: " + ", ".join(unknown_keys))
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
    timeout_seconds = config.get("timeout_seconds", 300)
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 3600
    ):
        errors.append("timeout_seconds must be an integer in [1, 3600]")
    health = config.get("health")
    if (
        not isinstance(health, dict)
        or set(health) != {"path", "expected_json"}
        or not isinstance(health.get("path"), str)
        or HEALTH_PATH_RE.fullmatch(health["path"]) is None
        or "//" in health["path"]
    ):
        errors.append("health.path must be an absolute HTTP path")
    else:
        expected = health.get("expected_json")
        if (
            not isinstance(expected, dict)
            or not expected
            or len(expected) > 16
            or not all(
                isinstance(key, str)
                and ENV_KEY_RE.fullmatch(key.upper()) is not None
                and type(value) in {str, int, float, bool}
                for key, value in expected.items()
            )
        ):
            errors.append("health.expected_json must be a small non-empty scalar object")
    secrets = config.get("secrets", [])
    if not isinstance(secrets, list):
        errors.append("secrets must be a list")
    else:
        seen_mounts: set[str] = set()
        seen_names: set[str] = set()
        for index, secret in enumerate(secrets):
            if not isinstance(secret, dict):
                errors.append(f"secrets[{index}] must be an object")
                continue
            if set(secret) != {"mount_path", "name", "version"}:
                errors.append(f"secrets[{index}] may contain only mount_path, name, and version")
                continue
            mount_path = secret["mount_path"]
            mount = PurePosixPath(mount_path) if isinstance(mount_path, str) else None
            if (
                mount is None
                or not mount.is_absolute()
                or mount.parent != PurePosixPath("/run/secrets")
                or mount.name in {"", ".", ".."}
                or str(mount) != mount_path
            ):
                errors.append(f"secrets[{index}].mount_path must be below /run/secrets")
            elif mount_path in seen_mounts:
                errors.append(f"secrets[{index}].mount_path is duplicated")
            else:
                seen_mounts.add(mount_path)
            secret_name = secret["name"]
            if not isinstance(secret_name, str) or not NAME_RE.fullmatch(secret_name):
                errors.append(f"secrets[{index}].name is invalid")
            elif secret_name in seen_names:
                errors.append(f"secrets[{index}].name is duplicated")
            else:
                seen_names.add(secret_name)
            if not isinstance(secret["version"], str) or not secret["version"].isdigit():
                errors.append(f"secrets[{index}].version must be an immutable numeric version")
    environment = config.get("environment", {})
    if not isinstance(environment, dict) or len(environment) > 32:
        errors.append("environment must be an object with at most 32 entries")
    else:
        for key, value in environment.items():
            key_is_valid = isinstance(key, str) and ENV_KEY_RE.fullmatch(key) is not None
            value_is_valid = isinstance(value, str) and ENV_VALUE_RE.fullmatch(value) is not None
            sensitive_name = key_is_valid and any(
                marker in key for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY")
            )
            file_reference = key_is_valid and key.endswith("_FILE")
            if (
                not key_is_valid
                or not value_is_valid
                or (sensitive_name and not file_reference)
                or (file_reference and value not in seen_mounts)
            ):
                errors.append(f"environment entry is unsafe: {key}")
    return errors


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"INVALID_JSON_CONSTANT:{value}")


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
        f"--timeout={config.get('timeout_seconds', 300)}s",
        f"--revision-suffix={config['release_id']}", f"--tag=candidate-{config['release_id']}",
        "--no-allow-unauthenticated", "--no-traffic", "--quiet", "--format=json",
    ]
    secrets = config.get("secrets", [])
    if secrets:
        references = ",".join(
            f"{item['mount_path']}={item['name']}:{item['version']}" for item in secrets
        )
        command.append(f"--set-secrets={references}")
    environment = config.get("environment", {})
    if environment:
        values = ",".join(f"{key}={environment[key]}" for key in sorted(environment))
        command.append(f"--set-env-vars={values}")
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
    if ACTOR_RE.fullmatch(executor) is None:
        raise ControlError("EXECUTOR_IDENTITY_INVALID")
    if not isinstance(approver, str) or ACTOR_RE.fullmatch(approver) is None or approver == executor:
        raise ControlError("AUTHORIZATION_REQUIRES_SEPARATE_APPROVER")
    try:
        expires = dt.datetime.fromisoformat(str(auth["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ControlError("AUTHORIZATION_EXPIRY_INVALID") from exc
    if expires.tzinfo is None or expires.utcoffset() is None:
        raise ControlError("AUTHORIZATION_EXPIRY_MUST_INCLUDE_TIMEZONE")
    now = dt.datetime.now(dt.UTC)
    if expires <= now:
        raise ControlError("AUTHORIZATION_EXPIRED")
    if expires > now + MAX_AUTHORIZATION_LIFETIME:
        raise ControlError("AUTHORIZATION_LIFETIME_EXCEEDS_24_HOURS")
    return auth


def _run(command: list[str], *, timeout: int = PROVIDER_COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    if not command or Path(command[0]).name != "gcloud":
        raise ControlError("ONLY_GCLOUD_COMMANDS_ARE_ALLOWED")
    executable = shutil.which(command[0])
    if not executable:
        raise ControlError("GCLOUD_NOT_INSTALLED")
    try:
        completed = subprocess.run(  # noqa: S603 - validated executable and structured arguments.
            [executable, *command[1:]],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ControlError(f"GCLOUD_TIMEOUT:{command[1]}:{timeout}") from exc
    if completed.returncode:
        message = (completed.stderr or completed.stdout or "provider command failed")[-2_000:]
        raise ControlError(f"GCLOUD_FAILED:{command[1]}:{message.replace(chr(10), ' ')}")
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


def _describe_optional(config: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return _describe(config)
    except ControlError as error:
        message = str(error).lower()
        if "not found" in message or "does not exist" in message:
            return None
        raise


def _traffic_is_exact(service: dict[str, Any], revision: str) -> bool:
    traffic = service.get("status", {}).get("traffic", [])
    return isinstance(traffic, list) and any(
        isinstance(item, dict)
        and item.get("revisionName") == revision
        and item.get("percent") == 100
        for item in traffic
    )


def _wait_for_traffic(config: dict[str, Any], revision: str, *, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _traffic_is_exact(_describe(config), revision):
            return
        time.sleep(2)
    raise ControlError("TRAFFIC_CONVERGENCE_TIMEOUT")


def _wait_for_candidate(config: dict[str, Any], tag: str, *, timeout: int = 120) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "CANDIDATE_TAG_NOT_OBSERVED"
    while time.monotonic() < deadline:
        service = _describe(config)
        try:
            candidate_probe_endpoints(service, tag)
        except ControlError as error:
            last_error = str(error)
            time.sleep(2)
            continue
        return service
    raise ControlError(f"CANDIDATE_CONVERGENCE_TIMEOUT:{last_error}")


def _wait_until_deleted(config: dict[str, Any], *, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _describe_optional(config) is None:
            return
        time.sleep(2)
    raise ControlError("SERVICE_DELETION_NOT_OBSERVED")


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
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
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
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ControlError("RECEIPT_OUTPUT_UNSAFE")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _identity_token(audience: str) -> str:
    executable = shutil.which("gcloud")
    if not executable:
        raise ControlError("GCLOUD_NOT_INSTALLED")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed provider operation and validated audience.
            [executable, "auth", "print-identity-token", f"--audiences={audience}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise ControlError("IDENTITY_TOKEN_COMMAND_TIMEOUT") from error
    token = completed.stdout.strip()
    if completed.returncode or not token or len(token.encode()) > MAX_IDENTITY_TOKEN_BYTES:
        raise ControlError("IDENTITY_TOKEN_REQUIRED_FOR_PRIVATE_HEALTH_PROBE")
    return token


def _private_health_request(config: dict[str, Any], uri: str, audience: str) -> None:
    token = _identity_token(audience)
    request = urllib.request.Request(  # noqa: S310 - provider-derived HTTPS URL is validated.
        uri.rstrip("/") + config["health"]["path"]
    )
    request.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=20) as response:  # noqa: S310 - validated provider-derived HTTPS.
        raw = response.read(MAX_HEALTH_BYTES + 1)
        if len(raw) > MAX_HEALTH_BYTES:
            raise ControlError("PRIVATE_HEALTH_RESPONSE_TOO_LARGE")
        if response.status != 200:
            raise ControlError("PRIVATE_HEALTH_HTTP_STATUS_INVALID")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ControlError("PRIVATE_HEALTH_JSON_INVALID") from error
    expected = config["health"]["expected_json"]
    if not isinstance(body, dict) or any(body.get(key) != value for key, value in expected.items()):
        raise ControlError("PRIVATE_HEALTH_CONTRACT_FAILED")


def _private_health_probe(config: dict[str, Any], service: dict[str, Any], tag: str) -> None:
    uri, audience = candidate_probe_endpoints(service, tag)
    _private_health_request(config, uri, audience)


def _private_service_health_probe(config: dict[str, Any], service: dict[str, Any]) -> None:
    service_url = service.get("status", {}).get("url")
    if not isinstance(service_url, str):
        raise ControlError("SERVICE_URL_NOT_OBSERVED")
    parsed = urlsplit(service_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".run.app")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ControlError("SERVICE_URL_INVALID")
    _private_health_request(config, service_url, service_url)


def execute_deploy(config: dict[str, Any], authorization: Path, executor: str, receipt_path: Path) -> None:
    preflight(config)
    auth = _authorization(authorization, "deploy", config, executor)
    before = _describe_optional(config)
    previous = before.get("status", {}).get("latestReadyRevisionName") if before else None
    _run(deploy_command(config))
    after = _describe(config)
    revision = after.get("status", {}).get("latestReadyRevisionName")
    if not isinstance(revision, str) or revision == previous:
        raise ControlError("NEW_READY_REVISION_NOT_OBSERVED")
    tag = f"candidate-{config['release_id']}"
    candidate = _wait_for_candidate(config, tag)
    _private_health_probe(config, candidate, tag)
    promote = [
        "gcloud", "run", "services", "update-traffic", config["service_name"],
        f"--project={config['project_id']}", f"--region={config['region']}",
        f"--to-revisions={revision}=100", "--quiet", "--format=json",
    ]
    _run(promote)
    _wait_for_traffic(config, revision)
    _private_service_health_probe(config, _describe(config))
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
    _wait_for_traffic(config, revision)
    _private_service_health_probe(config, _describe(config))
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
    _wait_until_deleted(config)
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
    config: dict[str, Any] | None = None
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
    except (ControlError, OSError, ValueError, json.JSONDecodeError) as exc:
        if args.action in {"deploy", "rollback", "destroy"} and args.execute:
            failure_receipt = {
                "schema_version": 1,
                "action": args.action,
                "status": "failed",
                "failed_at": dt.datetime.now(dt.UTC).isoformat(),
                "executor": args.executor,
                "error_code": str(exc).split(":", 1)[0],
                "provider_mutation_status": "UNKNOWN_RECONCILIATION_REQUIRED",
                "orphan_and_billing_review": "REQUIRED",
                "certification_effect": "NONE_REQUIRES_INDEPENDENT_GATE",
            }
            if config is not None:
                failure_receipt["config_digest"] = _canonical_digest(config)
            try:
                _write_receipt(args.receipt, failure_receipt)
            except (ControlError, OSError) as receipt_error:
                print(f"ERROR: FAILURE_RECEIPT_NOT_WRITTEN:{receipt_error}", file=sys.stderr)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
