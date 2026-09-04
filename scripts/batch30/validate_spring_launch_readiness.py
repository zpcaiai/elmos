#!/usr/bin/env python3
"""Fail-closed launch gate for the narrow Spring design-partner offer."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "deploy/production/spring-launch-profile.json"
COMPOSE = ROOT / "deploy/production/compose/docker-compose.production.yml"
SPRING_APPLICATION_COMPOSE = ROOT / "deploy/production/compose/docker-compose.spring-application.yml"
ENV_EXAMPLE = ROOT / "deploy/production/elmos-commercial.env.example"
CATALOG = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringRouteCatalog.java"
LOCAL_PORT = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/LocalSpringUpgradeExecutionPort.java"
WORKER_CONFIG = ROOT / "apps/java-engine-worker/src/main/resources/application.yml"
WORKER_POM = ROOT / "apps/java-engine-worker/pom.xml"
STUDIO = ROOT / "apps/web-console/app/spring/SpringModernizationStudio.tsx"
ENGINE_AUTH = ROOT / "apps/web-console/app/api/spring-upgrades/springEngineAuth.ts"
ENGINE_FILTER = ROOT / "apps/java-engine-worker/src/main/java/io/elmos/worker/SpringEngineRequestAuthenticationFilter.java"

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

REQUIRED_TRUE_ENVIRONMENT = (
    "ELMOS_SPRING_PROXY_ENABLED",
    "ELMOS_SPRING_PROXY_MULTI_TENANT",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
)
REQUIRED_FALSE_ENVIRONMENT = (
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
    "ELMOS_SPRING_CODING_AGENT_ENABLED",
)
SPRING_URL_ENVIRONMENT = (
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
)
SPRING_SECRET_PATH_ENVIRONMENT = (
    "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH",
    "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
    "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
)
SPRING_ENVIRONMENT_ALLOWLIST = frozenset(
    REQUIRED_TRUE_ENVIRONMENT
    + REQUIRED_FALSE_ENVIRONMENT
    + SPRING_URL_ENVIRONMENT
    + SPRING_SECRET_PATH_ENVIRONMENT
    + (
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    )
)
FORBIDDEN_SINGLE_TENANT_ENVIRONMENT = "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID"
MAX_ENVIRONMENT_FILE_BYTES = 64 * 1024
ENVIRONMENT_ASSIGNMENT = re.compile(r"([A-Z][A-Z0-9_]*)=(.*)")
SAFE_ENVIRONMENT_VALUE = re.compile(r"[A-Za-z0-9._~:/@,+%=-]*")
EXACT_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def has_symbolic_link_parent(path: Path) -> bool:
    return any(stat.S_ISLNK(parent.lstat().st_mode) for parent in path.parents)


def stable_file_metadata(details: os.stat_result) -> tuple[int, ...]:
    """Metadata that must remain unchanged across a security-sensitive read."""
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def is_placeholder(value: str) -> bool:
    upper = value.upper()
    return (
        not value
        or upper in {"UNKNOWN", "TODO", "TBD", "NOT_CONFIGURED", "CHANGE_ME"}
        or upper.startswith(("CHANGE_ME_", "PLACEHOLDER_", "TODO_", "TBD_"))
    )


def valid_https_endpoint(value: str) -> bool:
    """Accept an exact production HTTPS endpoint without credentials or local hosts."""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").rstrip(".").lower()
        _ = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or bool(parsed.fragment)
        or host == "localhost"
        or host.endswith((".localhost", ".invalid"))
    ):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_loopback
        or address.is_unspecified
        or address.is_link_local
        or address.is_multicast
    )


def parse_environment_file(errors: list[str], path: Path) -> dict[str, str]:
    """Parse a small Spring-only environment file as data, never as shell code."""
    if not path.is_absolute():
        errors.append("Spring environment file path must be absolute")
        return {}
    try:
        if has_symbolic_link_parent(path):
            errors.append("Spring environment file must not traverse symbolic-link parent directories")
            return {}
    except OSError:
        errors.append("Spring environment file is missing or unreadable")
        return {}
    try:
        details = path.lstat()
    except OSError:
        errors.append("Spring environment file is missing or unreadable")
        return {}
    if stat.S_ISLNK(details.st_mode):
        errors.append("Spring environment file must not be a symbolic link")
        return {}
    if not stat.S_ISREG(details.st_mode):
        errors.append("Spring environment file must be a regular file")
        return {}
    if details.st_nlink != 1:
        errors.append("Spring environment file must not be hard-linked")
        return {}
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append("Spring environment file is missing or unreadable")
        return {}
    if resolved.is_relative_to(ROOT.resolve()):
        errors.append("Spring environment file must be mounted from outside the repository")
        return {}

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        errors.append("Spring environment file is missing, unreadable, or not a regular non-symlink file")
        return {}
    raw = b""
    try:
        opened_details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_details.st_mode)
            or stable_file_metadata(opened_details) != stable_file_metadata(details)
        ):
            errors.append("Spring environment file changed while it was being validated")
            return {}
        mode = stat.S_IMODE(opened_details.st_mode)
        if opened_details.st_uid != os.getuid():
            errors.append("Spring environment file must be owned by the current user")
            return {}
        if mode not in {0o400, 0o600}:
            errors.append("Spring environment file permissions must be 0400 or 0600")
            return {}
        if opened_details.st_size > MAX_ENVIRONMENT_FILE_BYTES:
            errors.append("Spring environment file exceeds the 65536-byte limit")
            return {}
        chunks: list[bytes] = []
        remaining = MAX_ENVIRONMENT_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after_read_details = os.fstat(descriptor)
        after_read_path_details = path.lstat()
        if (
            stable_file_metadata(after_read_details) != stable_file_metadata(opened_details)
            or stable_file_metadata(after_read_path_details) != stable_file_metadata(opened_details)
            or len(raw) != opened_details.st_size
        ):
            errors.append("Spring environment file identity or size changed while it was being read")
            return {}
    except OSError:
        errors.append("Spring environment file changed or became unreadable while it was being read")
        return {}
    finally:
        os.close(descriptor)
    if len(raw) > MAX_ENVIRONMENT_FILE_BYTES:
        errors.append("Spring environment file exceeds the 65536-byte limit")
        return {}
    try:
        contents = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("Spring environment file must be valid UTF-8")
        return {}

    values: dict[str, str] = {}
    seen: set[str] = set()
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.strip():
            errors.append(f"Spring environment file line {line_number} has leading or trailing whitespace")
            continue
        match = ENVIRONMENT_ASSIGNMENT.fullmatch(line)
        if not match:
            errors.append(f"Spring environment file line {line_number} must be an exact KEY=VALUE assignment")
            continue
        name, value = match.groups()
        if name in seen:
            errors.append(f"Spring environment file line {line_number} duplicates {name}")
            continue
        seen.add(name)
        if name not in SPRING_ENVIRONMENT_ALLOWLIST:
            errors.append(f"Spring environment file line {line_number} uses unknown key {name}")
            continue
        if not SAFE_ENVIRONMENT_VALUE.fullmatch(value):
            errors.append(
                f"Spring environment file line {line_number} contains forbidden interpolation, quoting, whitespace, or command syntax"
            )
            continue
        values[name] = value
    return values


def effective_environment(file_values: Mapping[str, str]) -> dict[str, str]:
    """Overlay explicit process values on the parsed file without empty-value fallback."""
    values = dict(file_values)
    for name in SPRING_ENVIRONMENT_ALLOWLIST | {FORBIDDEN_SINGLE_TENANT_ENVIRONMENT}:
        if name in os.environ:
            values[name] = os.environ[name]
    return values


def inspect_secret_file(
    path: Path,
) -> tuple[bool, tuple[int, int] | None, bytes | None, str | None]:
    """Return stable inode and content identities for a bounded non-symlink secret."""
    if not path.is_absolute():
        return False, None, None, "must use an absolute path"
    try:
        if has_symbolic_link_parent(path):
            return False, None, None, "must not traverse symbolic-link parent directories"
        path_details = path.lstat()
    except OSError:
        return False, None, None, None
    if path_details.st_nlink != 1:
        return False, None, None, "must not be hard-linked"
    if (
        not stat.S_ISREG(path_details.st_mode)
        or stat.S_ISLNK(path_details.st_mode)
        or not 32 <= path_details.st_size <= 4096
        or stat.S_IMODE(path_details.st_mode) not in {0o400, 0o600}
    ):
        return False, None, None, None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return False, None, None, None
    try:
        opened_details = os.fstat(descriptor)
        identity = (opened_details.st_dev, opened_details.st_ino)
        if (
            not stat.S_ISREG(opened_details.st_mode)
            or stable_file_metadata(opened_details) != stable_file_metadata(path_details)
            or not 32 <= opened_details.st_size <= 4096
            or stat.S_IMODE(opened_details.st_mode) not in {0o400, 0o600}
            or opened_details.st_nlink != 1
        ):
            return False, None, None, "changed before it could be read"
        chunks: list[bytes] = []
        remaining = 4097
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        contents = b"".join(chunks)
        after_read_details = os.fstat(descriptor)
        after_read_path_details = path.lstat()
        if (
            stable_file_metadata(after_read_details) != stable_file_metadata(opened_details)
            or stable_file_metadata(after_read_path_details) != stable_file_metadata(opened_details)
            or len(contents) != opened_details.st_size
        ):
            return False, None, None, "changed while it was being read"
        return True, identity, hashlib.sha256(contents).digest(), None
    except OSError:
        return False, None, None, "changed or became unreadable while it was being read"
    finally:
        os.close(descriptor)


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
    worker_pom = WORKER_POM.read_text(encoding="utf-8")
    studio = STUDIO.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")
    spring_application_compose = SPRING_APPLICATION_COMPOSE.read_text(encoding="utf-8")
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    engine_auth = ENGINE_AUTH.read_text(encoding="utf-8")
    engine_filter = ENGINE_FILTER.read_text(encoding="utf-8")
    require(errors, f'LAUNCH_ROUTE_ID = "{EXPECTED_ROUTE}"' in catalog, "Java catalog lacks exact launch route authority")
    require(errors, "experimentalRoutesEnabled && request.allowExperimentalRoutes()" in local_port, "experimental route authorization is not operator AND request bound")
    require(errors, "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED:false" in worker_config, "worker experimental default is not false")
    require(errors, "operatorExperimentalRoutesEnabled" in studio and "disabled={capability?.operatorExperimentalRoutesEnabled !== true}" in studio, "console does not fail closed on operator experimental policy")
    require(errors, 'ELMOS_SPRING_PROXY_ENABLED: "${ELMOS_SPRING_PROXY_ENABLED:-false}"' in compose, "production Spring proxy is not env-gated")
    require(errors, 'ELMOS_SPRING_PROXY_MULTI_TENANT: "true"' in compose, "production Spring proxy is not explicitly multi-tenant")
    require(errors, "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH" not in compose, "base production deployment must not require the Spring engine HMAC file")
    require(errors, compose.count('ELMOS_SPRING_ENGINE_AUTH_ENABLED: "true"') == 1, "Spring worker must require service authentication")
    require(errors, spring_application_compose.count('ELMOS_SPRING_ENGINE_AUTH_ENABLED: "true"') == 1, "Spring activation overlay must authenticate the BFF")
    require(errors, spring_application_compose.count("ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH") == 2, "Spring activation overlay must mount one engine HMAC into exactly two consumers")
    require(errors, "java-engine-worker:" in spring_application_compose and "condition: service_started" in spring_application_compose, "Spring activation overlay must fail closed when the worker profile is omitted")
    require(errors, "X-ELMOS-Engine-Body-SHA256" in engine_auth and "X-ELMOS-Engine-Signature" in engine_auth, "Spring BFF request signing is not body bound")
    require(errors, "BODY_SHA256" in engine_filter and "nonces.putIfAbsent" in engine_filter, "Spring worker request authentication lacks body binding or replay rejection")
    require(errors, "micrometer-registry-prometheus" in worker_pom, "Spring worker must include the Prometheus registry")
    require(errors, "include: health,info,prometheus" in worker_config, "Spring worker must expose internal health and Prometheus endpoints")
    require(errors, 'ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED: "false"' in compose, "production experimental routes must be hard disabled")
    require(errors, 'ELMOS_SPRING_CODING_AGENT_ENABLED: "false"' in compose, "production long-tail coding agent must be hard disabled")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in env_example, "production env template still declares a single-tenant Spring identity")


def validate_external(
    errors: list[str],
    path: Path,
    *,
    trust_store: Path,
    evidence_roots: list[Path],
    expected_revision: str | None,
    expected_trust_store_digest: str | None,
    expected_environment_id: str | None,
    expected_deployment_id: str | None,
    expected_provider: str | None,
    expected_region: str | None,
    expected_environment_class: str | None,
    expected_configuration_digest: str | None,
) -> dict | None:
    initial_error_count = len(errors)
    if not path.is_absolute():
        errors.append("external evidence path must be absolute")
        return None
    try:
        if has_symbolic_link_parent(path):
            errors.append("external evidence must not traverse symbolic-link parent directories")
            return None
        resolved = path.resolve(strict=True)
        details = path.lstat()
    except OSError:
        errors.append("external evidence file is missing")
        return None
    require(errors, resolved.is_file() and not path.is_symlink(), "external evidence must be a regular non-symlink file")
    require(errors, not resolved.is_relative_to(ROOT.resolve()), "external evidence must be mounted from outside the repository")
    require(errors, details.st_uid == os.getuid(), "external evidence file must be owned by the current user")
    require(errors, stat.S_IMODE(details.st_mode) in {0o400, 0o600}, "external evidence file permissions must be 0400 or 0600")
    require(errors, details.st_nlink == 1, "external evidence file must not be hard-linked")
    if len(errors) != initial_error_count:
        return None
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.batch30.spring_launch_evidence import (
            verify_spring_launch_receipt_file,
        )

        result = verify_spring_launch_receipt_file(
            path,
            trust_store=trust_store,
            evidence_roots=evidence_roots,
            expected_revision=expected_revision,
            expected_profile_path=PROFILE,
            expected_trust_store_digest=expected_trust_store_digest,
            expected_environment_id=expected_environment_id,
            expected_deployment_id=expected_deployment_id,
            expected_provider=expected_provider,
            expected_region=expected_region,
            expected_environment_class=expected_environment_class,
            expected_configuration_digest=expected_configuration_digest,
            repo_root=ROOT,
        )
    except (OSError, ValueError) as error:
        errors.append(f"external evidence authentication failed: {error}")
        return None
    require(errors, result.get("evidence_status") == "VERIFIED_EXTERNAL_RECEIPT", "external evidence was not cryptographically verified")
    require(errors, result.get("external_evidence_intake") == "VALIDATED_NOT_CERTIFIED", "external evidence intake state drift")
    require(errors, result.get("certification") == "NOT_CERTIFIED", "external evidence must not self-certify")
    require(errors, result.get("certification_promoted") is False, "external evidence must not promote certification")
    if len(errors) != initial_error_count:
        return None
    return result


def validate_environment(errors: list[str], environment: Mapping[str, str]) -> None:
    for name in REQUIRED_TRUE_ENVIRONMENT:
        require(errors, environment.get(name) == "true", f"{name} must equal true")
    for name in REQUIRED_FALSE_ENVIRONMENT:
        require(errors, environment.get(name, "false") == "false", f"{name} must equal false")
    require(errors, not environment.get(FORBIDDEN_SINGLE_TENANT_ENVIRONMENT, "").strip(), "single-tenant Spring identity is forbidden")
    verifier_id = environment.get("ELMOS_SPRING_UPGRADE_VERIFIER_ID", "").strip()
    require(
        errors,
        EXACT_IDENTITY.fullmatch(verifier_id) is not None and not is_placeholder(verifier_id),
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID must be an exact non-placeholder identity",
    )
    for name in SPRING_URL_ENVIRONMENT:
        require(errors, valid_https_endpoint(environment.get(name, "")), f"{name} must use a non-local absolute https URL without credentials or fragments")
    workspace = Path(environment.get("ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH", ""))
    workspace_valid = False
    if workspace.is_absolute() and workspace != Path("/"):
        try:
            workspace_valid = (
                workspace.is_dir()
                and not workspace.is_symlink()
                and not has_symbolic_link_parent(workspace)
                and not workspace.resolve(strict=True).is_relative_to(ROOT.resolve())
            )
        except OSError:
            workspace_valid = False
    require(errors, workspace_valid, "shared Spring workspace must be an existing absolute non-symlink directory outside the repository")
    secret_paths: list[Path] = []
    secret_identities: list[tuple[int, int]] = []
    secret_digests: list[bytes] = []
    for name in SPRING_SECRET_PATH_ENVIRONMENT:
        path = Path(environment.get(name, ""))
        secret_paths.append(path)
        valid, identity, digest, failure = inspect_secret_file(path)
        if not valid:
            errors.append(f"{name} {failure}" if failure else f"{name} must be an owner-only regular 32-4096 byte file")
        if identity is not None and digest is not None:
            secret_identities.append(identity)
            secret_digests.append(digest)
    require(
        errors,
        len({os.path.normpath(str(path)) for path in secret_paths}) == len(SPRING_SECRET_PATH_ENVIRONMENT),
        "Spring HMAC secrets must use four distinct paths",
    )
    if len(secret_identities) == len(SPRING_SECRET_PATH_ENVIRONMENT):
        require(errors, len(set(secret_identities)) == len(secret_identities), "Spring HMAC secrets must use four distinct files/inodes")
        require(errors, len(set(secret_digests)) == len(secret_digests), "Spring HMAC secrets must use four distinct secret values")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the bounded Spring launch profile without executing environment-file contents.",
        epilog=(
            "Environment files accept only allowlisted KEY=VALUE data. Explicit process environment "
            "variables take precedence over file values; an explicit empty value remains empty and fails closed."
        ),
    )
    parser.add_argument("--external-evidence", type=Path)
    parser.add_argument("--trust-store", type=Path)
    parser.add_argument("--evidence-root", action="append", type=Path, default=[])
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-trust-store-digest")
    parser.add_argument("--expected-environment-id")
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-provider")
    parser.add_argument("--expected-region")
    parser.add_argument("--expected-environment-class", choices=("STAGING", "PRODUCTION"))
    parser.add_argument("--require-production-evidence", action="store_true")
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument(
        "--environment-file",
        type=Path,
        help="load an owner-only Spring environment file from outside the repository; implies --check-environment",
    )
    args = parser.parse_args()
    errors: list[str] = []
    profile = load(PROFILE)
    validate_contract(errors, profile)
    validate_code(errors)
    file_environment = parse_environment_file(errors, args.environment_file) if args.environment_file else {}
    check_environment = args.check_environment or args.environment_file is not None
    effective = effective_environment(file_environment)
    configuration_digest: str | None = None
    if check_environment:
        validate_environment(errors, effective)
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from scripts.batch30.spring_launch_evidence import (
                spring_environment_configuration_digest,
            )

            configuration_digest = spring_environment_configuration_digest(effective)
        except (OSError, ValueError) as error:
            errors.append(f"Spring environment configuration digest failed: {error}")

    if args.require_production_evidence:
        required_production_arguments = {
            "--environment-file": args.environment_file,
            "--expected-trust-store-digest": args.expected_trust_store_digest,
            "--expected-environment-id": args.expected_environment_id,
            "--expected-deployment-id": args.expected_deployment_id,
            "--expected-provider": args.expected_provider,
            "--expected-region": args.expected_region,
            "--expected-environment-class": args.expected_environment_class,
        }
        for option, value in required_production_arguments.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"production evidence requires {option}")

    if args.external_evidence and not args.require_production_evidence:
        required_intake_arguments = {
            "--environment-file": args.environment_file,
            "--expected-trust-store-digest": args.expected_trust_store_digest,
            "--expected-environment-id": args.expected_environment_id,
            "--expected-deployment-id": args.expected_deployment_id,
            "--expected-provider": args.expected_provider,
            "--expected-region": args.expected_region,
            "--expected-environment-class": args.expected_environment_class,
        }
        for option, value in required_intake_arguments.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"external evidence intake requires {option}")

    external_result: dict | None = None
    if args.external_evidence:
        if args.trust_store is None:
            errors.append("--trust-store is required with --external-evidence")
        if not args.evidence_root:
            errors.append("at least one --evidence-root is required with --external-evidence")
        if args.trust_store is not None and args.evidence_root:
            external_result = validate_external(
                errors,
                args.external_evidence,
                trust_store=args.trust_store,
                evidence_roots=args.evidence_root,
                expected_revision=args.expected_revision,
                expected_trust_store_digest=args.expected_trust_store_digest,
                expected_environment_id=args.expected_environment_id,
                expected_deployment_id=args.expected_deployment_id,
                expected_provider=args.expected_provider,
                expected_region=args.expected_region,
                expected_environment_class=args.expected_environment_class,
                expected_configuration_digest=configuration_digest,
            )
    elif args.require_production_evidence:
        errors.append("production evidence is required but --external-evidence was not supplied")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2 if args.require_production_evidence or args.external_evidence or check_environment else 1
    print(
        "SPRING_LAUNCH_GATE="
        + ("EXTERNAL_GATE_VERIFIED_NOT_CERTIFIED" if external_result else "READY_FOR_EXTERNAL_GATE")
    )
    if check_environment:
        print("ENVIRONMENT_PRECEDENCE=PROCESS_ENVIRONMENT_OVER_FILE")
        print(f"SPRING_CONFIGURATION_DIGEST={configuration_digest}")
    print("EXTERNAL_EVIDENCE_INTAKE=" + ("VALIDATED_NOT_CERTIFIED" if args.external_evidence else "NOT_RUN"))
    print("CERTIFICATION=NOT_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
