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
from urllib.parse import urlparse

from external_provider_adapter import (
    SUPPORTED_PROVIDER_ADAPTERS,
    ProviderAdapterError,
    validate_provider_binding,
)
from hosted_pitr_adapter import (
    SUPPORTED_PITR_DRIVERS,
    PitrAdapterError,
    validate_pitr_binding,
)
from external_verifier_crypto import (
    VerifierCryptoError,
    validate_receipt_time,
    verify_receipt_signature,
)


EXPECTED_PACKAGE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"
EXPECTED_PACKAGE = "elmos-production-runtime-skillpack-v1.2.0"
OPERATIONS = (
    "provider_runtime",
    "target_cluster_load",
    "chaos",
    "worker_process_kill",
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
SHA256 = re.compile(r"[0-9a-f]{64}")
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
        leaf = re.sub(r"\[[0-9]+\]$", "", path.rsplit(".", 1)[-1]).lower()
        if leaf in {
            "token",
            "api_token",
            "access_token",
            "refresh_token",
            "password",
            "private_key",
            "secret_value",
            "client_secret",
        }:
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
    try:
        validate_provider_binding(provider)
    except ProviderAdapterError as exc:
        raise ContractError(str(exc)) from exc

    target_load = operations["target_cluster_load"]
    for field in ("scheduler_base_url_env", "billing_base_url_env", "gate_token_env"):
        require_env_name(target_load.get(field), f"operations.target_cluster_load.{field}")
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
        if not isinstance(case.get("recovery_resource"), str) or not case["recovery_resource"]:
            raise ContractError(f"operations.chaos.cases[{index}] lacks a recovery_resource")

    worker_kill = operations["worker_process_kill"]
    for field in ("context", "namespace", "selector", "recovery_resource"):
        if not isinstance(worker_kill.get(field), str) or not worker_kill[field]:
            raise ContractError(f"operations.worker_process_kill.{field} is required")
    if not isinstance(worker_kill.get("minimum_ready_replicas"), int) \
            or not 2 <= worker_kill["minimum_ready_replicas"] <= 1_000:
        raise ContractError("worker process kill minimum_ready_replicas must be between 2 and 1000")

    redis_loss = operations["redis_loss"]
    require_env_name(redis_loss.get("redis_url_env"), "operations.redis_loss.redis_url_env")
    if not isinstance(redis_loss.get("allow_flush"), bool):
        raise ContractError("operations.redis_loss.allow_flush must be boolean")
    if not isinstance(redis_loss.get("dedicated_ephemeral_cache"), bool):
        raise ContractError("operations.redis_loss.dedicated_ephemeral_cache must be boolean")
    if not isinstance(redis_loss.get("database_index"), int) or not 0 <= redis_loss["database_index"] <= 15:
        raise ContractError("operations.redis_loss.database_index must be between 0 and 15")
    if not isinstance(redis_loss.get("resource_id"), str) or not redis_loss["resource_id"]:
        raise ContractError("operations.redis_loss.resource_id is required")
    redis_digest = redis_loss.get("endpoint_sha256")
    if not is_placeholder(redis_digest) and (
        not isinstance(redis_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", redis_digest)
    ):
        raise ContractError("operations.redis_loss.endpoint_sha256 must be lowercase SHA-256")

    try:
        validate_pitr_binding(operations["backup_pitr"])
    except PitrAdapterError as exc:
        raise ContractError(str(exc)) from exc

    independent = operations["independent_verification"]
    require_env_name(independent.get("endpoint_env"), "operations.independent_verification.endpoint_env")
    require_env_name(independent.get("credential_env"), "operations.independent_verification.credential_env")
    for field in ("producer_actor", "verifier_actor"):
        if not isinstance(independent.get(field), str) or not independent[field]:
            raise ContractError(f"operations.independent_verification.{field} is required")
    if independent["producer_actor"] == independent["verifier_actor"]:
        raise ContractError("producer and independent verifier actors must differ")
    require_env_name(independent.get("public_key_env"), "operations.independent_verification.public_key_env")
    key_digest = independent.get("public_key_sha256")
    if not is_placeholder(key_digest) and (
        not isinstance(key_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", key_digest)
    ):
        raise ContractError("independent verifier public_key_sha256 must be lowercase SHA-256")
    if independent.get("signature_algorithm") != "SHA256_WITH_PEM_KEY":
        raise ContractError("independent verifier signature_algorithm is unsupported")
    maximum_age = independent.get("max_receipt_age_seconds")
    if not isinstance(maximum_age, int) or not 60 <= maximum_age <= 3600:
        raise ContractError("independent verifier max_receipt_age_seconds must be between 60 and 3600")

    deployment = operations["production_deployment"]
    for field in ("context", "namespace", "release", "resource_prefix"):
        if not isinstance(deployment.get(field), str) or not deployment[field]:
            raise ContractError(f"operations.production_deployment.{field} is required")
    resource_prefix = deployment["resource_prefix"]
    if not is_placeholder(resource_prefix) and not re.fullmatch(
        r"[a-z0-9](?:[-a-z0-9]{0,51}[a-z0-9])?", resource_prefix
    ):
        raise ContractError(
            "production deployment resource_prefix must be a Kubernetes DNS label of at most 53 characters"
        )
    if not is_placeholder(resource_prefix):
        expected_scheduler = f"deployment/{resource_prefix}-scheduler"
        expected_worker = f"statefulset/{resource_prefix}-worker"
        if any(
            case.get("resource") != expected_scheduler
            or case.get("recovery_resource") != expected_scheduler
            for case in chaos["cases"]
        ):
            raise ContractError("chaos resources do not bind the production resource prefix")
        if worker_kill.get("recovery_resource") != expected_worker:
            raise ContractError("worker-kill resource does not bind the production resource prefix")
    relative_repo_dir(root, deployment.get("chart"), "operations.production_deployment.chart")
    images = deployment.get("image_digests")
    if not isinstance(images, dict) or set(images) != {"controlPlane", "worker"}:
        raise ContractError("production deployment must bind controlPlane and worker image digests")
    for name, digest in images.items():
        if is_placeholder(digest):
            continue
        if not isinstance(digest, str) or not OCI_IMAGE_AT_DIGEST.fullmatch(digest):
            raise ContractError(f"production deployment OCI image reference is not digest-pinned: {name}")
    supply_chain = deployment.get("supply_chain")
    if not isinstance(supply_chain, dict):
        raise ContractError("production deployment must bind a supply-chain verification contract")
    require_env_name(
        supply_chain.get("signing_key_env"),
        "operations.production_deployment.supply_chain.signing_key_env")
    key_digest = supply_chain.get("signing_key_sha256")
    if not is_placeholder(key_digest) and (
            not isinstance(key_digest, str) or not SHA256.fullmatch(key_digest)):
        raise ContractError("supply-chain signing_key_sha256 must be lowercase SHA-256")
    if supply_chain.get("signature_verification") != "cosign-key-v1":
        raise ContractError("unsupported supply-chain signature verification contract")
    if supply_chain.get("sbom_predicate_type") != "https://cyclonedx.org/bom":
        raise ContractError("supply-chain SBOM predicate must be CycloneDX")
    if supply_chain.get("provenance_predicate_type") != "https://slsa.dev/provenance/v1":
        raise ContractError("supply-chain provenance predicate must be SLSA v1")
    require_env_name(
        deployment.get("values_file_env"),
        "operations.production_deployment.values_file_env")
    values_digest = deployment.get("values_file_sha256")
    if not is_placeholder(values_digest) and (
        not isinstance(values_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", values_digest)
    ):
        raise ContractError("production deployment values_file_sha256 must be lowercase SHA-256")
    if deployment.get("atomic") is not True or deployment.get("wait") is not True:
        raise ContractError("production deployment must be atomic and wait for readiness")
    if not isinstance(deployment.get("timeout"), str) or not HELM_TIMEOUT.fullmatch(deployment["timeout"]):
        raise ContractError("production deployment timeout must be a positive Helm duration")
    if chaos.get("context") != deployment.get("context") or chaos.get("namespace") != deployment.get("namespace"):
        raise ContractError("chaos and production deployment must bind the same cluster context and namespace")
    if worker_kill.get("context") != deployment.get("context") or worker_kill.get("namespace") != deployment.get("namespace"):
        raise ContractError("worker kill and production deployment must bind the same cluster context and namespace")
    if deployment.get("disable_gate_after_validation") is not True:
        raise ContractError("production deployment must disable the gate after validation")

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
        ("redis_loss", "redis_url_env"),
        ("independent_verification", "endpoint_env"),
        ("independent_verification", "credential_env"),
        ("independent_verification", "public_key_env"),
        ("production_deployment", "supply_chain.signing_key_env"),
    ):
        if "." in field:
            parent, child = field.split(".", 1)
            env_name = operations[operation].get(parent, {}).get(child)
        else:
            env_name = operations[operation].get(field)
        if isinstance(env_name, str) and not is_placeholder(env_name) and not env.get(env_name):
            blockers[operation].append(f"environment variable {env_name} is not set")

    target_load = operations["target_cluster_load"]
    shared_gate_fields = ("scheduler_base_url_env", "gate_token_env")
    for operation in ("target_cluster_load", "chaos", "worker_process_kill", "redis_loss"):
        fields = ("scheduler_base_url_env", "billing_base_url_env", "gate_token_env") \
            if operation == "target_cluster_load" else shared_gate_fields
        for field in fields:
            env_name = target_load.get(field)
            if isinstance(env_name, str) and not is_placeholder(env_name) and not env.get(env_name):
                blockers[operation].append(f"environment variable {env_name} is not set")
    for field in ("scheduler_base_url_env", "billing_base_url_env"):
        env_name = target_load.get(field)
        value = env.get(env_name, "") if isinstance(env_name, str) else ""
        if value:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username \
                    or parsed.password or parsed.query or parsed.fragment:
                blockers["target_cluster_load"].append(
                    f"environment variable {env_name} must be a credential-free HTTPS base URL")

    binaries = {
        "target_cluster_load": ("k6",),
        "chaos": ("kubectl",),
        "worker_process_kill": ("kubectl",),
        "redis_loss": ("redis-cli",),
        "production_deployment": ("helm", "cosign", "kubectl"),
    }
    for operation, required in binaries.items():
        for binary in required:
            if shutil.which(binary) is None:
                blockers[operation].append(f"required binary {binary} is not installed")

    provider_adapter = operations["provider_runtime"].get("adapter")
    if not is_placeholder(provider_adapter) and provider_adapter not in SUPPORTED_PROVIDER_ADAPTERS:
        blockers["provider_runtime"].append("provider adapter is not repository-supported")
    pitr_driver = operations["backup_pitr"].get("driver")
    if not is_placeholder(pitr_driver):
        if pitr_driver not in SUPPORTED_PITR_DRIVERS:
            blockers["backup_pitr"].append("PITR driver is not repository-supported")
        else:
            binary = {
                "aws-rds-postgresql-v1": "aws",
                "gcp-cloudsql-postgresql-v1": "gcloud",
                "azure-postgresql-flexible-v1": "az",
            }[pitr_driver]
            if shutil.which(binary) is None:
                blockers["backup_pitr"].append(f"required binary {binary} is not installed")
            if shutil.which("psql") is None:
                blockers["backup_pitr"].append("required binary psql is not installed")
            for field in (
                "source_database_url_env",
                "restore_username_env",
                "restore_password_env",
            ):
                env_name = operations["backup_pitr"].get(field)
                if isinstance(env_name, str) and not is_placeholder(env_name) and not env.get(env_name):
                    blockers["backup_pitr"].append(f"environment variable {env_name} is not set")
    if not operations["redis_loss"].get("allow_flush", False):
        blockers["redis_loss"].append("destructive Redis flush is not explicitly authorized in the plan")
    if not operations["redis_loss"].get("dedicated_ephemeral_cache", False):
        blockers["redis_loss"].append("Redis target is not declared as a dedicated ephemeral cache")
    redis_env = operations["redis_loss"].get("redis_url_env")
    redis_url = env.get(redis_env, "") if isinstance(redis_env, str) else ""
    if redis_url:
        parsed = urlparse(redis_url)
        expected_db = operations["redis_loss"].get("database_index")
        try:
            actual_db = int((parsed.path or "/0").lstrip("/") or "0")
        except ValueError:
            actual_db = -1
        if parsed.scheme != "rediss" or not parsed.hostname or actual_db != expected_db:
            blockers["redis_loss"].append(
                "Redis URL must use rediss and bind the exact planned database index")
        else:
            canonical = f"rediss://{parsed.hostname}:{parsed.port or 6379}/{actual_db}"
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if digest != operations["redis_loss"].get("endpoint_sha256"):
                blockers["redis_loss"].append("Redis endpoint digest does not match the plan")
    deployment = operations["production_deployment"]
    values_env = deployment.get("values_file_env")
    if isinstance(values_env, str) and not is_placeholder(values_env):
        values_path_value = env.get(values_env)
        if not values_path_value:
            blockers["production_deployment"].append(
                f"environment variable {values_env} is not set")
        else:
            values_path = Path(values_path_value)
            if values_path.is_symlink() or not values_path.is_file():
                blockers["production_deployment"].append(
                    "Helm values file is not a regular non-symlink file")
            elif sha256(values_path) != deployment.get("values_file_sha256"):
                blockers["production_deployment"].append(
                    "Helm values file digest does not match the plan")
    public_key_env = operations["independent_verification"].get("public_key_env")
    if isinstance(public_key_env, str) and env.get(public_key_env):
        public_key = Path(env[public_key_env])
        if public_key.is_symlink() or not public_key.is_file():
            blockers["independent_verification"].append("verifier public key is not a regular non-symlink file")
        elif sha256(public_key) != operations["independent_verification"].get("public_key_sha256"):
            blockers["independent_verification"].append("verifier public key digest does not match the plan")
    supply_key = operations["production_deployment"]["supply_chain"]
    supply_key_env = supply_key.get("signing_key_env")
    if isinstance(supply_key_env, str) and env.get(supply_key_env):
        signing_key = Path(env[supply_key_env])
        if signing_key.is_symlink() or not signing_key.is_file():
            blockers["production_deployment"].append(
                "supply-chain signing key is not a regular non-symlink file")
        elif sha256(signing_key) != supply_key.get("signing_key_sha256"):
            blockers["production_deployment"].append(
                "supply-chain signing key digest does not match the plan")
    verifier_key = operations["independent_verification"].get("public_key_sha256")
    signing_key_digest = supply_key.get("signing_key_sha256")
    if not is_placeholder(verifier_key) and not is_placeholder(signing_key_digest) \
            and verifier_key == signing_key_digest:
        blockers["production_deployment"].append(
            "image signing key and independent verifier key must be distinct")
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
    if requested & {"chaos", "worker_process_kill", "redis_loss", "backup_pitr", "production_deployment"} and authorization.get("allow_destructive_operations") is not True:
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
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ContractError("independent verifier response is not a JSON object")
    for field in ("verification_id", "verified_at", "signature", "signing_key_sha256"):
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
    env = os.environ if environ is None else environ
    public_key_name = operation["public_key_env"]
    public_key_value = env.get(public_key_name)
    if not public_key_value:
        raise ContractError(f"environment variable {public_key_name} is not set")
    try:
        validate_receipt_time(receipt, operation["max_receipt_age_seconds"])
        verify_receipt_signature(
            receipt,
            Path(public_key_value),
            operation["public_key_sha256"],
        )
    except VerifierCryptoError as exc:
        raise ContractError(str(exc)) from exc
    return receipt
