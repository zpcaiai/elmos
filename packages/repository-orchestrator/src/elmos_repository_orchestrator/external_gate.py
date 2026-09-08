"""Fail-closed external execution and production certification gate.

This module validates evidence produced by real providers.  It never turns a
local test, a configured credential, or a producer assertion into external or
certification evidence.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import (
    ContractError,
    canonical_json,
    normalize_relative_path,
    parse_timestamp,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
)


OPERATIONS = (
    "elasticsearch",
    "dify",
    "model_provider",
    "otel_collector",
    "multimodal_ocr",
    "multimodal_asr",
    "multimodal_vision",
    "representative_workload",
    "production_deployment",
    "independent_verification",
)
EXECUTION_STATUSES = frozenset({"NOT_CONFIGURED", "NOT_RUN", "PASS", "FAIL", "UNKNOWN"})
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40,64}$")
PLACEHOLDER_PREFIXES = ("REQUIRED_", "REPLACE_WITH_")
SIGNED_CERTIFICATE_FIELDS = (
    "schema_version",
    "gate_id",
    "decision",
    "report_digest",
    "evidence_set_digest",
    "repository_revision",
    "artifact_digest",
    "certifier_actor",
    "certifier_organization",
    "certified_at",
    "expires_at",
    "public_key_sha256",
)


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIXES)


def _walk(value: Any, path: str = ""):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}" if path else str(key))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
    else:
        yield path, value


def _reject_inline_secrets(value: Mapping[str, Any]) -> None:
    sensitive = {
        "api_key",
        "api_token",
        "access_token",
        "authorization",
        "client_secret",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
    }
    for path, item in _walk(value):
        leaf = re.sub(r"\[[0-9]+\]$", "", path.rsplit(".", 1)[-1]).lower()
        if leaf in sensitive:
            raise ContractError("inline_secret", f"{path} must name an environment variable instead")
        if isinstance(item, str) and item.lower().startswith(("bearer ", "basic ")):
            raise ContractError("inline_secret", f"{path} contains inline authorization material")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _validate_operation_inventory(value: Any, field_name: str) -> Mapping[str, Any]:
    operations = require_mapping(value, field_name)
    if set(operations) != set(OPERATIONS):
        raise ContractError("operation_inventory", f"{field_name} must contain the exact required operations")
    return operations


def validate_external_plan(plan_value: Any) -> Mapping[str, Any]:
    """Validate the checked-in external plan without accessing providers."""

    plan = require_mapping(plan_value, "external_plan")
    if plan.get("schema_version") != 1:
        raise ContractError("plan_schema", "external plan schema_version must be 1")
    require_string(plan.get("gate_id"), "external_plan.gate_id")
    require_string(plan.get("subject"), "external_plan.subject")
    producer = require_string(plan.get("producer_actor"), "external_plan.producer_actor")
    certifier = require_mapping(plan.get("certification"), "external_plan.certification")
    certifier_actor = require_string(certifier.get("certifier_actor"), "certification.certifier_actor")
    require_string(certifier.get("certifier_organization"), "certification.certifier_organization")
    if producer == certifier_actor:
        raise ContractError("self_certification", "producer and production certifier must differ")
    if certifier.get("signature_algorithm") != "SHA256_WITH_PEM_KEY":
        raise ContractError("signature_algorithm", "unsupported certification signature algorithm")
    key_digest = require_string(certifier.get("trusted_public_key_sha256"), "certification.trusted_public_key_sha256")
    if not _is_placeholder(key_digest) and not SHA256.fullmatch(key_digest):
        raise ContractError("key_digest", "trusted public-key digest must be SHA-256")
    maximum_age = certifier.get("max_certificate_age_seconds")
    if isinstance(maximum_age, bool) or not isinstance(maximum_age, int) or not 60 <= maximum_age <= 604800:
        raise ContractError("certificate_age", "max certificate age must be between 60 and 604800 seconds")

    operations = _validate_operation_inventory(plan.get("operations"), "external_plan.operations")
    for operation_name in OPERATIONS:
        operation = require_mapping(operations[operation_name], f"operations.{operation_name}")
        if operation.get("status") != "NOT_RUN":
            raise ContractError("predeclared_result", f"{operation_name} must start as NOT_RUN")
        require_string(operation.get("evidence_role"), f"operations.{operation_name}.evidence_role")
        env_names = require_string_sequence(operation.get("required_env", ()), f"operations.{operation_name}.required_env")
        if any(not ENV_NAME.fullmatch(name) for name in env_names):
            raise ContractError("environment_name", f"{operation_name} has an invalid environment-variable name")
    if plan.get("production_certification") != "NOT_CERTIFIED":
        raise ContractError("predeclared_certification", "external plan cannot predeclare certification")
    _reject_inline_secrets(plan)
    return plan


def external_preflight(plan_value: Any, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Report configuration readiness while preserving every operation as NOT_RUN."""

    plan = validate_external_plan(plan_value)
    environment = os.environ if environ is None else environ
    blockers: dict[str, list[str]] = {}
    operations = require_mapping(plan["operations"], "external_plan.operations")
    for operation_name in OPERATIONS:
        operation = require_mapping(operations[operation_name], f"operations.{operation_name}")
        missing = [name for name in operation.get("required_env", ()) if not environment.get(name)]
        if missing:
            blockers[operation_name] = [f"missing_environment:{name}" for name in missing]
    certification = require_mapping(plan["certification"], "certification")
    key_digest = certification["trusted_public_key_sha256"]
    if _is_placeholder(key_digest):
        blockers.setdefault("independent_verification", []).append("trusted_public_key_sha256_not_pinned")
    if _is_placeholder(certification["certifier_organization"]):
        blockers.setdefault("independent_verification", []).append("certifier_organization_not_bound")
    return {
        "status": "BLOCKED" if blockers else "READY",
        "external_execution": {operation: "NOT_RUN" for operation in OPERATIONS},
        "production_certification": "NOT_CERTIFIED",
        "blockers": blockers,
    }


def _safe_evidence_file(evidence_root: Path, relative: Any) -> Path:
    normalized = normalize_relative_path(relative, "evidence.path")
    try:
        root = evidence_root.resolve(strict=True)
    except OSError as exc:
        raise ContractError("evidence_root", "evidence root does not exist") from exc
    if not root.is_dir():
        raise ContractError("evidence_root", "evidence root must be a directory")
    candidate = root / normalized
    if candidate.is_symlink() or not candidate.is_file():
        raise ContractError("evidence_unavailable", f"evidence is not a regular non-symlink file: {normalized}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ContractError("evidence_escape", f"evidence escapes its root: {normalized}") from exc
    return resolved


def validate_external_report(
    plan_value: Any,
    report_value: Any,
    *,
    evidence_root: Path,
) -> tuple[Mapping[str, Any], tuple[Mapping[str, str], ...]]:
    """Validate exact operation outcomes and digest-bound evidence files."""

    plan = validate_external_plan(plan_value)
    report = require_mapping(report_value, "external_report")
    if report.get("schema_version") != 1 or report.get("gate_id") != plan["gate_id"]:
        raise ContractError("report_binding", "external report schema or gate binding is invalid")
    revision = require_string(report.get("repository_revision"), "external_report.repository_revision")
    if not REVISION.fullmatch(revision):
        raise ContractError("revision_binding", "repository revision must be an exact hexadecimal commit")
    artifact_digest = require_string(report.get("artifact_digest"), "external_report.artifact_digest")
    if not SHA256.fullmatch(artifact_digest):
        raise ContractError("artifact_binding", "artifact digest must be SHA-256")
    require_string(report.get("environment"), "external_report.environment")
    producer = require_string(report.get("producer_actor"), "external_report.producer_actor")
    if producer != plan["producer_actor"]:
        raise ContractError("producer_binding", "external report producer does not match the plan")
    parse_timestamp(report.get("generated_at"), "external_report.generated_at")
    if report.get("production_certification") != "NOT_CERTIFIED":
        raise ContractError("producer_certification", "producer report may only state NOT_CERTIFIED")

    plan_operations = require_mapping(plan["operations"], "external_plan.operations")
    operations = _validate_operation_inventory(report.get("operations"), "external_report.operations")
    evidence_items: list[Mapping[str, str]] = []
    for operation_name in OPERATIONS:
        operation = require_mapping(operations[operation_name], f"operations.{operation_name}")
        status = operation.get("status")
        if status not in EXECUTION_STATUSES:
            raise ContractError("execution_status", f"{operation_name} has an invalid status")
        if operation.get("evidence_role") != require_mapping(
            plan_operations[operation_name], f"plan.operations.{operation_name}"
        ).get("evidence_role"):
            raise ContractError("evidence_role", f"{operation_name} evidence role does not match the plan")
        executor = require_string(operation.get("executor_actor"), f"operations.{operation_name}.executor_actor")
        verifier = require_string(operation.get("verifier_actor"), f"operations.{operation_name}.verifier_actor")
        if executor == verifier:
            raise ContractError("self_verification", f"{operation_name} executor and verifier must differ")
        evidence = operation.get("evidence", ())
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes, bytearray)):
            raise ContractError("evidence_array", f"{operation_name} evidence must be an array")
        if status == "PASS" and not evidence:
            raise ContractError("missing_evidence", f"{operation_name} PASS requires evidence")
        if status == "PASS":
            require_string(operation.get("authorization_id"), f"operations.{operation_name}.authorization_id")
            if operation.get("synthetic") is not False:
                raise ContractError("synthetic_evidence", f"{operation_name} PASS evidence must be non-synthetic")
        for item_value in evidence:
            item = require_mapping(item_value, f"operations.{operation_name}.evidence[]")
            path = normalize_relative_path(item.get("path"), "evidence.path")
            digest = require_string(item.get("sha256"), "evidence.sha256")
            if not SHA256.fullmatch(digest):
                raise ContractError("evidence_digest", f"{operation_name} evidence digest must be SHA-256")
            if _sha256_file(_safe_evidence_file(evidence_root, path)) != digest:
                raise ContractError("evidence_tamper", f"{operation_name} evidence digest mismatch: {path}")
            evidence_items.append({"operation": operation_name, "path": path, "sha256": digest})
    return report, tuple(sorted(evidence_items, key=lambda item: (item["operation"], item["path"])))


def certificate_signing_bytes(certificate_value: Any) -> bytes:
    certificate = require_mapping(certificate_value, "certificate")
    payload = {field: certificate.get(field) for field in SIGNED_CERTIFICATE_FIELDS}
    return (canonical_json(payload) + "\n").encode("utf-8")


def _verify_signature(certificate: Mapping[str, Any], public_key: Path) -> None:
    if public_key.is_symlink() or not public_key.is_file():
        raise ContractError("public_key", "trusted public key must be a regular non-symlink file")
    try:
        signature = base64.b64decode(certificate.get("signature", ""), validate=True)
    except (TypeError, ValueError) as exc:
        raise ContractError("certificate_signature", "certificate signature is invalid base64") from exc
    if not 64 <= len(signature) <= 16384:
        raise ContractError("certificate_signature", "certificate signature length is invalid")
    with tempfile.TemporaryDirectory(prefix="elmos-ai-certify-") as temporary:
        payload_path = Path(temporary) / "certificate.json"
        signature_path = Path(temporary) / "certificate.sig"
        payload_path.write_bytes(certificate_signing_bytes(certificate))
        signature_path.write_bytes(signature)
        try:
            result = subprocess.run(
                [
                    "openssl",
                    "dgst",
                    "-sha256",
                    "-verify",
                    str(public_key),
                    "-signature",
                    str(signature_path),
                    str(payload_path),
                ],
                capture_output=True,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise ContractError("certificate_verifier", "OpenSSL certificate verifier is unavailable") from exc
    if result.returncode != 0:
        raise ContractError("certificate_signature", "independent certificate signature verification failed")


def evaluate_production_certification(
    plan_value: Any,
    report_value: Any,
    *,
    evidence_root: Path,
    certificate_value: Any | None = None,
    public_key: Path | None = None,
    now: datetime | None = None,
    signature_verifier: Callable[[Mapping[str, Any], Path], None] | None = None,
) -> dict[str, Any]:
    """Return CERTIFIED only for a complete, fresh, independently signed evidence set."""

    plan = validate_external_plan(plan_value)
    report, evidence = validate_external_report(plan, report_value, evidence_root=evidence_root)
    operation_results = require_mapping(report["operations"], "external_report.operations")
    reasons = [
        f"{name}:{require_mapping(operation_results[name], f'operations.{name}').get('status')}"
        for name in OPERATIONS
        if require_mapping(operation_results[name], f"operations.{name}").get("status") != "PASS"
    ]
    if reasons:
        return {
            "status": "BLOCKED",
            "production_certification": "NOT_CERTIFIED",
            "certified": False,
            "report_digest": sha256_payload(report),
            "evidence_set_digest": sha256_payload(evidence),
            "reasons": reasons,
        }
    if certificate_value is None or public_key is None:
        return {
            "status": "BLOCKED",
            "production_certification": "NOT_CERTIFIED",
            "certified": False,
            "report_digest": sha256_payload(report),
            "evidence_set_digest": sha256_payload(evidence),
            "reasons": ["independent_certificate_missing"],
        }

    certificate = require_mapping(certificate_value, "certificate")
    certification = require_mapping(plan["certification"], "certification")
    if _is_placeholder(certification["certifier_organization"]):
        raise ContractError("untrusted_certifier", "independent certifier organization is not bound")
    report_digest = sha256_payload(report)
    evidence_digest = sha256_payload(evidence)
    expected = {
        "schema_version": 1,
        "gate_id": plan["gate_id"],
        "decision": "CERTIFIED",
        "report_digest": report_digest,
        "evidence_set_digest": evidence_digest,
        "repository_revision": report["repository_revision"],
        "artifact_digest": report["artifact_digest"],
        "certifier_actor": certification["certifier_actor"],
        "certifier_organization": certification["certifier_organization"],
    }
    for field, value in expected.items():
        if certificate.get(field) != value:
            raise ContractError("certificate_binding", f"certificate {field} does not bind the report")
    certified_at = parse_timestamp(certificate.get("certified_at"), "certificate.certified_at")
    expires_at = parse_timestamp(certificate.get("expires_at"), "certificate.expires_at")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    maximum_age = certification["max_certificate_age_seconds"]
    if certified_at > current or (current - certified_at).total_seconds() > maximum_age or expires_at <= current:
        raise ContractError("certificate_time", "certificate is future-dated, stale, or expired")
    if public_key.is_symlink() or not public_key.is_file():
        raise ContractError("public_key", "trusted public key must be a regular non-symlink file")
    key_digest = _sha256_file(public_key)
    if _is_placeholder(certification["trusted_public_key_sha256"]):
        raise ContractError("untrusted_certifier", "certifier public-key digest is not pinned")
    if key_digest != certification["trusted_public_key_sha256"] or certificate.get("public_key_sha256") != key_digest:
        raise ContractError("untrusted_certifier", "certificate public key does not match the pinned trust root")
    (signature_verifier or _verify_signature)(certificate, public_key)
    return {
        "status": "READY",
        "production_certification": "CERTIFIED",
        "certified": True,
        "report_digest": report_digest,
        "evidence_set_digest": evidence_digest,
        "certificate_digest": sha256_payload(certificate),
        "reasons": [],
    }
