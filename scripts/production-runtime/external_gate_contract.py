#!/usr/bin/env python3
"""Shared fail-closed contract helpers for external production-gate runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_PACKAGE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"
EXPECTED_PACKAGE = "elmos-production-runtime-skillpack-v1.2.0"
OPERATIONS = (
    "provider_runtime",
    "target_cluster_load",
    "chaos",
    "redis_loss",
    "backup_pitr",
    "independent_verification",
    "production_deployment",
)
EXTERNAL_STATUSES = {"NOT_RUN", "PASS", "FAIL", "UNKNOWN"}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
OCI_IMAGE_AT_DIGEST = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9._-]+)+@sha256:[0-9a-f]{64}$"
)
HELM_TIMEOUT = re.compile(r"^[1-9][0-9]*(?:s|m|h)$")
PLACEHOLDER_PREFIXES = ("REQUIRED", "REPLACE_WITH_")


class ContractError(ValueError):
    pass


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and (not value.strip() or value.startswith(PLACEHOLDER_PREFIXES))


def require_env_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ENV_NAME.fullmatch(value):
        raise ContractError(f"{field} must be an uppercase environment-variable name")
    return value


def relative_repo_path(root: Path, value: Any, field: str, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ContractError(f"{field} must be a repository-relative path")
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ContractError(f"{field} escapes the repository root") from exc
    if must_exist and not candidate.is_file():
        raise ContractError(f"{field} does not exist: {value}")
    return candidate


def relative_repo_dir(root: Path, value: Any, field: str) -> Path:
    candidate = relative_repo_path(root, value, field, must_exist=False)
    if not candidate.is_dir():
        raise ContractError(f"{field} does not exist as a directory: {value}")
    return candidate


def _walk_values(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_values(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f"{path}[{index}]")
    else:
        yield path, value


def _reject_inline_secrets(plan: dict[str, Any]) -> None:
    for path, value in _walk_values(plan):
        lowered = path.lower()
        if any(marker in lowered for marker in ("token", "password", "private_key", "secret_value")):
            raise ContractError(f"{path} must not contain inline secret material")
        if isinstance(value, str) and value.startswith("Bearer "):
            raise ContractError(f"{path} contains inline authorization material")


def validate_plan(plan: dict[str, Any], root: Path) -> None:
    if plan.get("schema_version") != 1:
        raise ContractError("external gate plan schema_version must be 1")
    package = plan.get("package")
    if not isinstance(package, dict):
        raise ContractError("package binding is required")
    if package.get("name") != EXPECTED_PACKAGE or package.get("version") != "1.2.0":
        raise ContractError("external gate plan package identity is incorrect")
    if package.get("archive_sha256") != EXPECTED_PACKAGE_SHA256:
        raise ContractError("external gate plan is not bound to the pinned source archive")
    archive = relative_repo_path(root, package.get("archive"), "package.archive")
    if sha256(archive) != EXPECTED_PACKAGE_SHA256:
        raise ContractError("external gate package archive bytes do not match the pinned digest")

    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise ContractError("execution binding is required")
    for field in ("environment", "region", "change_id"):
        if not isinstance(execution.get(field), str) or not execution[field]:
            raise ContractError(f"execution.{field} is required")
    if is_placeholder(execution["environment"]) or is_placeholder(execution["region"]):
        # Placeholders are valid in the checked-in template, but are surfaced by
        # preflight rather than silently treated as an executable environment.
        pass

    operations = plan.get("operations")
    if not isinstance(operations, dict) or set(operations) != set(OPERATIONS):
        raise ContractError("operation inventory must exactly match the external gate contract")
    for operation in OPERATIONS:
        value = operations[operation]
        if not isinstance(value, dict):
            raise ContractError(f"operations.{operation} must be an object")
        status = value.get("status")
        if status not in EXTERNAL_STATUSES:
            raise ContractError(f"operations.{operation}.status is invalid")
        if status != "NOT_RUN":
            raise ContractError(f"checked-in plan may not predeclare {operation} as {status}")

    provider = operations["provider_runtime"]
    require_env_name(provider.get("credential_env"), "operations.provider_runtime.credential_env")

    target_load = operations["target_cluster_load"]
    require_env_name(target_load.get("base_url_env"), "operations.target_cluster_load.base_url_env")
    relative_repo_path(root, target_load.get("script"), "operations.target_cluster_load.script")
    if not isinstance(target_load.get("vus"), int) or not 1 <= target_load["vus"] <= 1_000:
        raise ContractError("operations.target_cluster_load.vus must be between 1 and 1000")
    if not isinstance(target_load.get("duration"), str) or not target_load["duration"]:
        raise ContractError("operations.target_cluster_load.duration is required")

    chaos = operations["chaos"]
    if not isinstance(chaos.get("cases"), list) or not chaos["cases"]:
        raise ContractError("operations.chaos.cases must be non-empty")
    for index, case in enumerate(chaos["cases"]):
        if not isinstance(case, dict) or not isinstance(case.get("id"), str):
            raise ContractError(f"operations.chaos.cases[{index}] must have an id")
        if case.get("action") not in {"rollout_restart", "delete_pod"}:
            raise ContractError(f"operations.chaos.cases[{index}] has an unsupported action")
        if not isinstance(case.get("resource") or case.get("selector"), str):
            raise ContractError(f"operations.chaos.cases[{index}] lacks a target")

    redis_loss = operations["redis_loss"]
    require_env_name(redis_loss.get("redis_url_env"), "operations.redis_loss.redis_url_env")
    if not isinstance(redis_loss.get("allow_flush"), bool):
        raise ContractError("operations.redis_loss.allow_flush must be boolean")

    independent = operations["independent_verification"]
    require_env_name(independent.get("endpoint_env"), "operations.independent_verification.endpoint_env")
    require_env_name(independent.get("credential_env"), "operations.independent_verification.credential_env")
    for field in ("producer_actor", "verifier_actor"):
        if not isinstance(independent.get(field), str) or not independent[field]:
            raise ContractError(f"operations.independent_verification.{field} is required")
    if independent["producer_actor"] == independent["verifier_actor"]:
        raise ContractError("producer and independent verifier actors must differ")

    deployment = operations["production_deployment"]
    for field in ("context", "namespace", "release"):
        if not isinstance(deployment.get(field), str) or not deployment[field]:
            raise ContractError(f"operations.production_deployment.{field} is required")
    relative_repo_dir(root, deployment.get("chart"), "operations.production_deployment.chart")
    images = deployment.get("image_digests")
    if not isinstance(images, dict) or set(images) != {"controlPlane", "worker"}:
        raise ContractError("production deployment must bind controlPlane and worker image digests")
    for name, digest in images.items():
        if is_placeholder(digest):
            continue
        if not isinstance(digest, str) or not OCI_IMAGE_AT_DIGEST.fullmatch(digest):
            raise ContractError(f"production deployment OCI image reference is not digest-pinned: {name}")
    if deployment.get("atomic") is not True or deployment.get("wait") is not True:
        raise ContractError("production deployment must be atomic and wait for readiness")
    if not isinstance(deployment.get("timeout"), str) or not HELM_TIMEOUT.fullmatch(deployment["timeout"]):
        raise ContractError("production deployment timeout must be a positive Helm duration")
    if chaos.get("context") != deployment.get("context") or chaos.get("namespace") != deployment.get("namespace"):
        raise ContractError("chaos and production deployment must bind the same cluster context and namespace")

    if plan.get("production_certification") != "NOT_CERTIFIED":
        raise ContractError("external gate plan may not certify production")
    _reject_inline_secrets(plan)


def _missing(value: Any, path: str = "") -> list[str]:
    if isinstance(value, dict):
        missing: list[str] = []
        for key, child in value.items():
            if key == "status":
                continue
            missing.extend(_missing(child, f"{path}.{key}" if path else str(key)))
        return missing
    if isinstance(value, list):
        missing = []
        for index, child in enumerate(value):
            missing.extend(_missing(child, f"{path}[{index}]") )
        return missing
    return [path] if is_placeholder(value) else []


def preflight(plan: dict[str, Any], root: Path, environ: dict[str, str] | None = None) -> dict[str, list[str]]:
    env = os.environ if environ is None else environ
    operations = plan["operations"]
    blockers: dict[str, list[str]] = {operation: _missing(operations[operation]) for operation in OPERATIONS}
    execution = plan["execution"]
    if is_placeholder(execution["environment"]):
        blockers["_execution"] = ["execution.environment"]
    if is_placeholder(execution["region"]):
        blockers.setdefault("_execution", []).append("execution.region")
    if is_placeholder(execution["change_id"]):
        blockers.setdefault("_execution", []).append("execution.change_id")

    for operation, field in (
        ("provider_runtime", "credential_env"),
        ("target_cluster_load", "base_url_env"),
        ("redis_loss", "redis_url_env"),
        ("independent_verification", "endpoint_env"),
        ("independent_verification", "credential_env"),
    ):
        env_name = operations[operation].get(field)
        if isinstance(env_name, str) and not is_placeholder(env_name) and not env.get(env_name):
            blockers[operation].append(f"environment variable {env_name} is not set")

    binaries = {
        "target_cluster_load": "k6",
        "chaos": "kubectl",
        "redis_loss": "redis-cli",
        "production_deployment": "helm",
    }
    for operation, binary in binaries.items():
        if shutil.which(binary) is None:
            blockers[operation].append(f"required binary {binary} is not installed")

    blockers["provider_runtime"].append("provider-specific adapter implementation is required")
    blockers["backup_pitr"].append("backup-provider PITR adapter and restore target are required")
    if not operations["redis_loss"].get("allow_flush", False):
        blockers["redis_loss"].append("destructive Redis flush is not explicitly authorized in the plan")
    return {key: sorted(set(value)) for key, value in blockers.items() if value}


def validate_authorization(authorization: dict[str, Any], plan: dict[str, Any], requested: set[str]) -> None:
    if authorization.get("schema_version") != 1 or authorization.get("authorized") is not True:
        raise ContractError("authorization must be schema_version 1 with authorized=true")
    for field in ("actor", "environment", "change_id", "approval_id", "expires_at"):
        if not isinstance(authorization.get(field), str) or not authorization[field]:
            raise ContractError(f"authorization.{field} is required")
    try:
        expiry = datetime.fromisoformat(authorization["expires_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("authorization.expires_at must be ISO-8601") from exc
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ContractError("authorization has expired or has no timezone")
    execution = plan["execution"]
    if authorization["environment"] != execution["environment"]:
        raise ContractError("authorization environment does not match the plan")
    if authorization["change_id"] != execution["change_id"]:
        raise ContractError("authorization change_id does not match the plan")
    allowed = authorization.get("operations")
    if not isinstance(allowed, list) or not requested.issubset(set(allowed)):
        raise ContractError("authorization does not cover every requested operation")
    if requested & {"chaos", "redis_loss", "production_deployment"} and authorization.get("allow_destructive_operations") is not True:
        raise ContractError("destructive operation requires allow_destructive_operations=true")
    verifier = plan["operations"]["independent_verification"]["verifier_actor"]
    if authorization["actor"] == verifier:
        raise ContractError("executor may not also be the independent verifier")


def redact_command(command: list[str], secret_values: list[str] | None = None) -> list[str]:
    redacted = list(command)
    for secret in secret_values or []:
        if secret:
            redacted = [value.replace(secret, "<REDACTED>") for value in redacted]
    return redacted


def validate_verifier_receipt(
    receipt: Any,
    operation: dict[str, Any],
    report_sha256: str,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ContractError("independent verifier response is not a JSON object")
    for field in ("verification_id", "verified_at", "signature"):
        if not isinstance(receipt.get(field), str) or not receipt[field]:
            raise ContractError(f"independent verifier receipt is missing {field}")
    if receipt.get("status") != "PASS":
        raise ContractError("independent verifier did not return PASS")
    if receipt.get("report_sha256") != report_sha256:
        raise ContractError("independent verifier report digest binding mismatch")
    if receipt.get("producer_actor") != operation["producer_actor"]:
        raise ContractError("independent verifier producer actor binding mismatch")
    if receipt.get("verifier_actor") != operation["verifier_actor"]:
        raise ContractError("independent verifier actor binding mismatch")
    if receipt["producer_actor"] == receipt["verifier_actor"]:
        raise ContractError("producer and verifier actors are not independent")
    return receipt
