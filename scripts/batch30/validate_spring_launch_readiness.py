#!/usr/bin/env python3
"""Fail-closed launch gate for the narrow Spring design-partner offer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "deploy/production/spring-launch-profile.json"
COMPOSE = ROOT / "deploy/production/compose/docker-compose.production.yml"
ENV_EXAMPLE = ROOT / "deploy/production/elmos-commercial.env.example"
CATALOG = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java"
LOCAL_PORT = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java"
WORKER_CONFIG = ROOT / "apps/java-engine-worker/src/main/resources/application.yml"
STUDIO = ROOT / "apps/web-console/app/spring/SpringModernizationStudio.tsx"

EXPECTED_ROUTE = "boot-2.7-maven-to-boot-3.5.3-java-21"
EXPECTED_GATES = {
    "STAGING_DEPLOYMENT",
    "ROOTLESS_ISOLATION_ATTESTATION",
    "DEFAULT_DENY_NETWORK_ATTESTATION",
    "INDEPENDENT_VERIFICATION",
    "ROLLBACK_AND_RESTORE_DRILL",
    "DESIGN_PARTNER_ACCEPTANCE",
    "SECURITY_AND_PRIVACY_REVIEW",
    "OPERATIONS_SLO_SIGNOFF",
    "LEGAL_TAX_PAYMENT_READINESS",
}


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def validate_contract(errors: list[str], profile: dict) -> None:
    route = profile.get("launch_route", {})
    require(errors, profile.get("schema_version") == 1, "launch profile schema_version must be 1")
    require(errors, route.get("route_id") == EXPECTED_ROUTE, "launch route must remain the exact Boot 2.7 design-partner route")
    require(errors, route.get("source") == {"framework": "spring-boot", "version": "2.7.18", "java": "17", "build": "maven-3.9.11"}, "launch source tuple drift")
    require(errors, route.get("target") == {"framework": "spring-boot", "version": "3.5.3", "java": "21", "build": "maven-3.9.11"}, "launch target tuple drift")
    require(errors, route.get("commercial_status") == "DESIGN_PARTNER", "launch route must be DESIGN_PARTNER")
    require(errors, profile.get("tenant_mode") == "MULTI_TENANT", "production launch must not use the single-tenant fallback")
    require(errors, profile.get("execution_plane") == "PRIVATE_ROOTLESS_RUNNER_BROKER", "execution plane must be private rootless runner broker")
    experimental = profile.get("experimental_routes", {})
    require(errors, experimental.get("operator_default") is False, "experimental routes must default off")
    require(errors, experimental.get("request_opt_in_required") is True, "experimental routes require per-request opt-in")
    require(errors, profile.get("long_tail_coding_agent", {}).get("commercial_status") == "EXCLUDED_FROM_LAUNCH", "long-tail coding agent must be excluded from launch")
    require(errors, profile.get("repository_decision") == "READY_FOR_EXTERNAL_GATE", "repository decision must not claim production readiness")
    require(errors, profile.get("certification") == "NOT_CERTIFIED", "repository profile cannot claim certification")
    gates = profile.get("external_gates", [])
    require(errors, isinstance(gates, list) and len(gates) == len(EXPECTED_GATES) and all(isinstance(item, dict) for item in gates), "external gates must be nine exact objects")
    ids = {item.get("id") for item in gates if isinstance(item, dict)}
    require(errors, ids == EXPECTED_GATES, "external gate inventory drift")
    require(errors, all(item.get("status") == "NOT_RUN" for item in gates if isinstance(item, dict)), "checked-in external gates must remain NOT_RUN")


def validate_code(errors: list[str]) -> None:
    catalog = CATALOG.read_text(encoding="utf-8")
    local_port = LOCAL_PORT.read_text(encoding="utf-8")
    worker_config = WORKER_CONFIG.read_text(encoding="utf-8")
    studio = STUDIO.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    require(errors, f'LAUNCH_ROUTE_ID = "{EXPECTED_ROUTE}"' in catalog, "Java catalog lacks exact launch route authority")
    require(errors, "experimentalRoutesEnabled && request.allowExperimentalRoutes()" in local_port, "experimental route authorization is not operator AND request bound")
    require(errors, "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED:false" in worker_config, "worker experimental default is not false")
    require(errors, "operatorExperimentalRoutesEnabled" in studio and "disabled={capability?.operatorExperimentalRoutesEnabled !== true}" in studio, "console does not fail closed on operator experimental policy")
    require(errors, 'ELMOS_SPRING_PROXY_ENABLED: "${ELMOS_SPRING_PROXY_ENABLED:-false}"' in compose, "production Spring proxy is not env-gated")
    require(errors, 'ELMOS_SPRING_PROXY_MULTI_TENANT: "true"' in compose, "production Spring proxy is not explicitly multi-tenant")
    require(errors, 'ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED: "false"' in compose, "production experimental routes must be hard disabled")
    require(errors, 'ELMOS_SPRING_CODING_AGENT_ENABLED: "false"' in compose, "production long-tail coding agent must be hard disabled")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in env_example, "production env template still declares a single-tenant Spring identity")


def validate_external(errors: list[str], path: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
        details = path.lstat()
    except OSError:
        errors.append("external evidence file is missing")
        return
    require(errors, resolved.is_file() and not path.is_symlink(), "external evidence must be a regular non-symlink file")
    require(errors, not resolved.is_relative_to(ROOT.resolve()), "external evidence must be mounted from outside the repository")
    require(errors, details.st_mode & 0o077 == 0, "external evidence file must be owner-only")
    try:
        evidence = load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        errors.append("external evidence file is not valid JSON")
        return
    require(errors, evidence.get("schema_version") == 1, "external evidence schema_version must be 1")
    require(errors, evidence.get("route_id") == EXPECTED_ROUTE, "external evidence route mismatch")
    require(errors, bool(re.fullmatch(r"[0-9a-f]{40}", str(evidence.get("source_revision", "")))), "external evidence source_revision must be 40 lowercase hex")
    expected_profile_sha = hashlib.sha256(PROFILE.read_bytes()).hexdigest()
    require(errors, evidence.get("launch_profile_sha256") == expected_profile_sha, "external evidence launch_profile_sha256 mismatch")
    for field in ("artifact_sha256", "environment_digest"):
        require(errors, bool(re.fullmatch(r"[0-9a-f]{64}", str(evidence.get(field, "")))), f"external evidence {field} must be 64 lowercase hex")
    gates = evidence.get("gates", [])
    require(errors, isinstance(gates, list) and len(gates) == len(EXPECTED_GATES) and all(isinstance(item, dict) for item in gates), "external evidence gates must be nine exact objects")
    gate_map = {item.get("id"): item for item in gates if isinstance(item, dict)}
    require(errors, set(gate_map) == EXPECTED_GATES, "external evidence gate inventory drift")
    for gate_id in EXPECTED_GATES:
        item = gate_map.get(gate_id, {})
        require(errors, item.get("status") == "PASSED_EXTERNAL", f"external gate {gate_id} is not PASSED_EXTERNAL")
        evidence_uri = str(item.get("evidence_uri", "")).strip()
        require(errors, bool(re.fullmatch(r"(?:https|s3|gs|az)://[^\s]+", evidence_uri)), f"external gate {gate_id} lacks an approved immutable evidence_uri")
        require(errors, bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("evidence_sha256", "")))), f"external gate {gate_id} lacks evidence_sha256")
    executor = str(evidence.get("execution_identity", "")).strip()
    verifier = str(evidence.get("independent_verifier", "")).strip()
    reviewer = str(evidence.get("independent_reviewer", "")).strip()
    require(errors, bool(executor), "execution_identity is required")
    require(errors, bool(verifier) and verifier != executor, "independent_verifier must differ from execution_identity")
    require(errors, bool(reviewer) and reviewer not in {executor, verifier}, "independent_reviewer must be a third identity")
    approvers = evidence.get("approved_by", [])
    valid_approvers = (
        isinstance(approvers, list)
        and all(isinstance(item, str) and item.strip() for item in approvers)
        and len(set(approvers)) >= 2
    )
    require(errors, valid_approvers, "at least two distinct external approvers are required")
    partners = evidence.get("design_partner_organizations", [])
    valid_partners = (
        isinstance(partners, list)
        and all(isinstance(item, str) and item.strip() for item in partners)
        and len(set(partners)) >= 2
    )
    require(errors, valid_partners, "at least two distinct design-partner organizations are required")
    require(errors, bool(str(evidence.get("observed_at", "")).strip()), "observed_at is required")


def validate_environment(errors: list[str]) -> None:
    required_true = (
        "ELMOS_SPRING_PROXY_ENABLED",
        "ELMOS_SPRING_PROXY_MULTI_TENANT",
        "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
        "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
        "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
        "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
        "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    )
    required_false = (
        "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
        "ELMOS_SPRING_CODING_AGENT_ENABLED",
    )
    for name in required_true:
        require(errors, os.environ.get(name) == "true", f"{name} must equal true")
    for name in required_false:
        require(errors, os.environ.get(name, "false") == "false", f"{name} must equal false")
    require(errors, not os.environ.get("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID", "").strip(), "single-tenant Spring identity is forbidden")
    require(errors, bool(os.environ.get("ELMOS_SPRING_UPGRADE_VERIFIER_ID", "").strip()), "ELMOS_SPRING_UPGRADE_VERIFIER_ID is required")
    for name in (
        "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
        "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
        "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    ):
        require(errors, bool(re.fullmatch(r"https://[^\s/]+(?:/[^\s]*)?", os.environ.get(name, ""))), f"{name} must use an absolute https URL")
    workspace = Path(os.environ.get("ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH", ""))
    require(errors, workspace.is_absolute() and workspace.is_dir() and not workspace.is_symlink(), "shared Spring workspace must be an existing absolute non-symlink directory")
    secret_paths: list[Path] = []
    for name in (
        "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
        "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
        "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
    ):
        path = Path(os.environ.get(name, ""))
        secret_paths.append(path)
        valid = False
        try:
            details = path.lstat()
            valid = (
                path.is_absolute()
                and stat.S_ISREG(details.st_mode)
                and not stat.S_ISLNK(details.st_mode)
                and details.st_size >= 32
                and details.st_size <= 4096
                and details.st_mode & 0o077 == 0
            )
        except OSError:
            pass
        require(errors, valid, f"{name} must be an owner-only regular 32-4096 byte file")
    require(errors, len({str(path.resolve(strict=False)) for path in secret_paths}) == 3, "Spring HMAC secrets must use three distinct files")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-evidence", type=Path)
    parser.add_argument("--require-production-evidence", action="store_true")
    parser.add_argument("--check-environment", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    profile = load(PROFILE)
    validate_contract(errors, profile)
    validate_code(errors)
    if args.check_environment:
        validate_environment(errors)
    if args.external_evidence:
        validate_external(errors, args.external_evidence)
    elif args.require_production_evidence:
        errors.append("production evidence is required but --external-evidence was not supplied")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2 if args.require_production_evidence or args.external_evidence or args.check_environment else 1
    print("SPRING_LAUNCH_GATE=READY_FOR_EXTERNAL_GATE")
    print("EXTERNAL_EVIDENCE_INTAKE=" + ("VALIDATED_NOT_CERTIFIED" if args.external_evidence else "NOT_RUN"))
    print("CERTIFICATION=NOT_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
