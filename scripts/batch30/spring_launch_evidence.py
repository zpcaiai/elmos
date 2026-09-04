#!/usr/bin/env python3
"""Build references and verify signed Spring launch evidence receipts.

The module is deliberately an intake verifier, not an evidence producer.  It can
hash bytes already present below an explicitly approved root, calculate canonical
JSON digests, and verify Ed25519 envelopes against a separate trust store.  It
never creates a ``PASSED_EXTERNAL`` claim and it never signs on behalf of an
executor, verifier, reviewer, approver, or design partner.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (  # noqa: E402
    TrustedKey,
    TrustStore,
    canonical_bytes,
    canonical_digest,
    decode_signature,
    read_regular_file_once,
)

NAMESPACE = "batch30-spring-launch-external-evidence"
BUSINESS_LINE = "spring-legacy-modernization"
ROUTE_ID = "boot-2.7-maven-to-boot-3.5.3-java-21"
PROFILE = ROOT / "deploy" / "production" / "spring-launch-profile.json"
DEFAULT_MAX_AGE = timedelta(hours=72)
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_CONTENT_BYTES = 5 * 1024 * 1024 * 1024
MAX_GATE_EVIDENCE_BYTES = 512 * 1024 * 1024
ED25519_SPKI_DER_PREFIX = bytes.fromhex("302a300506032b6570032100")
ED25519_SIGNATURE_BYTES = 64

GATE_IDS = (
    "STAGING_DEPLOYMENT",
    "ROOTLESS_ISOLATION_ATTESTATION",
    "DEFAULT_DENY_NETWORK_ATTESTATION",
    "INDEPENDENT_VERIFICATION",
    "ROLLBACK_AND_RESTORE_DRILL",
    "DESIGN_PARTNER_ACCEPTANCE",
    "SECURITY_AND_PRIVACY_REVIEW",
    "OPERATIONS_SLO_SIGNOFF",
    "LEGAL_TAX_PAYMENT_READINESS",
)

EXECUTOR_ROLE = "spring-launch-evidence-executor"
VERIFIER_ROLE = "spring-launch-gate-verifier"
REVIEWER_ROLE = "spring-launch-independent-reviewer"
APPROVER_ROLE = "spring-launch-release-approver"
DESIGN_PARTNER_ROLE = "spring-launch-design-partner-approver"
INDEX_AUTHORITY_ROLE = "spring-launch-evidence-index-authority"
ALLOWED_ROLES = {
    EXECUTOR_ROLE,
    VERIFIER_ROLE,
    REVIEWER_ROLE,
    APPROVER_ROLE,
    DESIGN_PARTNER_ROLE,
    INDEX_AUTHORITY_ROLE,
}

# This is the byte-level handoff between the safe environment-file loader and
# the signed environment manifest.  Values are configuration or host paths;
# secret file contents are deliberately excluded.
SPRING_CONFIGURATION_ENV_KEYS = (
    "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    "ELMOS_SPRING_CODING_AGENT_ENABLED",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_PROXY_ENABLED",
    "ELMOS_SPRING_PROXY_MULTI_TENANT",
    "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
    "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID",
    "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
)

# Exact non-secret environment inputs which can change the effective Spring
# worker runtime.  Presence is part of the digest because Spring's
# ``${ENV:default}`` semantics distinguish an absent variable from an explicitly
# empty one.  File paths naming mounted secrets are configuration; secret bytes
# are never read here.
SPRING_WORKER_CONFIGURATION_ENV_KEYS = (
    "ELMOS_ALLOWED_GIT_HOSTS",
    "ELMOS_ALLOW_FILE_REPOSITORIES",
    "ELMOS_ENGINE_PORT",
    "ELMOS_GRADLE_EXECUTABLE",
    "ELMOS_MAVEN_DEPENDENCY_SEED",
    "ELMOS_MAVEN_EXECUTABLE",
    "ELMOS_OSV_API_BASE",
    "ELMOS_OSV_ENABLED",
    "ELMOS_SHUTDOWN_TIMEOUT",
    "ELMOS_SOURCE_JAVA_HOME",
    "ELMOS_SPRING_CODING_AGENT_ENABLED",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    "ELMOS_SPRING_ENGINE_AUTH_REPLAY_ROOT",
    "ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE",
    "ELMOS_SPRING_ENGINE_AUTH_WINDOW_SECONDS",
    "ELMOS_SPRING_LOCAL_ENGINEERING_ENABLED",
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    "ELMOS_SPRING_RUNTIME_RUNNER_SECRET_FILE",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_SECRET_FILE",
    "ELMOS_SPRING_UPGRADE_ENABLED",
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
    "ELMOS_SPRING_UPGRADE_GLOBAL_CAPACITY",
    "ELMOS_SPRING_UPGRADE_JAVA_HOMES",
    "ELMOS_SPRING_UPGRADE_LEASE_TTL_SECONDS",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_QUEUE_TTL_SECONDS",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_TENANT_CAPACITY",
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
    "ELMOS_SPRING_UPGRADE_VERIFIER_SECRET_FILE",
    "ELMOS_SPRING_UPGRADE_WORKSPACE_ROOT",
    "ELMOS_TARGET_JAVA_HOME",
    "ELMOS_WORKSPACE_ROOT",
)
# Repository-controlled image and Compose values.  Keeping these values
# explicit lets the launch gate independently calculate what docker inspect
# must report instead of trusting a digest supplied by an operator.
SPRING_WORKER_FIXED_ENVIRONMENT = {
    "ELMOS_ALLOW_FILE_REPOSITORIES": "false",
    "ELMOS_MAVEN_EXECUTABLE": "/usr/share/maven/bin/mvn",
    "ELMOS_SHUTDOWN_TIMEOUT": "30s",
    "ELMOS_SOURCE_JAVA_HOME": "/opt/java/openjdk-17",
    "ELMOS_SPRING_CODING_AGENT_ENABLED": "false",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED": "true",
    "ELMOS_SPRING_ENGINE_AUTH_REPLAY_ROOT": "/var/lib/elmos/spring-engine-auth-replay",
    "ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE": "/run/secrets/elmos-spring-engine-hmac",
    "ELMOS_SPRING_RUNTIME_RUNNER_SECRET_FILE": "/run/secrets/elmos-runtime-hmac",
    "ELMOS_SPRING_TRANSFORMER_BROKER_SECRET_FILE": "/run/secrets/elmos-transformer-hmac",
    "ELMOS_SPRING_UPGRADE_ENABLED": "true",
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED": "false",
    "ELMOS_SPRING_UPGRADE_JAVA_HOMES": "8=/opt/java/openjdk-8,11=/opt/java/openjdk-11",
    "ELMOS_SPRING_UPGRADE_VERIFIER_SECRET_FILE": "/run/secrets/elmos-verifier-hmac",
    "ELMOS_SPRING_UPGRADE_WORKSPACE_ROOT": "/workspace/private-runner",
    "ELMOS_TARGET_JAVA_HOME": "/opt/java/openjdk",
}
SPRING_WORKER_EXECUTION_ENVIRONMENT = {
    "PATH": "/opt/java/openjdk/bin:/usr/share/maven/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "JAVA_HOME": "/opt/java/openjdk",
    "MAVEN_HOME": "/usr/share/maven",
    "MAVEN_CONFIG": "/home/elmos/.m2",
    "MAVEN_VERSION": "3.9.11",
    "HOME": "/home/elmos",
    "LANG": "C.UTF-8",
    "LANGUAGE": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "JAVA_VERSION": "21",
}
SPRING_WORKER_DYNAMIC_ENV_KEYS = (
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
)
# The production Compose contract intentionally clears exactly these process
# overrides.  No relaxed spelling is accepted, and every value must remain the
# empty string.  Other Spring/server/management/JVM overrides must be absent.
SPRING_WORKER_ALLOWED_EXPLICIT_EMPTY_ENVIRONMENT = frozenset(
    {
        "SPRING_APPLICATION_JSON",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JAVA_OPTS",
        "JDK_JAVA_OPTIONS",
        "SERVER_SERVLET_CONTEXT_PATH",
        "SERVER_SERVLET_PATH",
        "SPRING_MVC_SERVLET_PATH",
    }
)
SPRING_WORKER_EFFECTIVE_ENV_KEYS = tuple(
    sorted(
        {
            *SPRING_WORKER_CONFIGURATION_ENV_KEYS,
            *SPRING_WORKER_ALLOWED_EXPLICIT_EMPTY_ENVIRONMENT,
            *SPRING_WORKER_EXECUTION_ENVIRONMENT,
        }
    )
)
SPRING_WORKER_CONTAINER_ENTRYPOINT = (
    "/opt/java/openjdk/bin/java",
    "-XX:MaxRAMPercentage=70",
    "-jar",
    "/app/app.jar",
)
REQUIRED_RUNTIME_IMAGE_NAMES = frozenset(
    {"worker", "web", "proxy", "transformer", "runner"}
)
WEB_CONSOLE_CONTAINER_ENTRYPOINT = ("/usr/local/bin/docker-entrypoint.sh",)
WEB_CONSOLE_CONTAINER_COMMAND = (
    "/usr/local/bin/node",
    "/workspace/apps/web-console/node_modules/next/dist/bin/next",
    "start",
    "--hostname",
    "0.0.0.0",
    "--port",
    "3000",
)
WEB_CONSOLE_CONFIGURATION_ENVIRONMENT = {
    "NODE_ENV": "production",
    "NEXT_TELEMETRY_DISABLED": "1",
    "HOSTNAME": "0.0.0.0",
    "PORT": "3000",
    "NODE_VERSION": "24.14.0",
    "YARN_VERSION": "1.22.22",
    "HOME": "/tmp",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "NODE_OPTIONS": "",
    "ELMOS_SPRING_PROXY_ENABLED": "true",
    "ELMOS_SPRING_PROXY_MULTI_TENANT": "true",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED": "true",
    "ELMOS_SPRING_ENGINE_AUTH_SECRET_FILE": "/run/secrets/elmos-spring-engine-hmac",
    "ELMOS_TRUSTED_INTERNAL_HTTP": "true",
    "JAVA_ENGINE_BASE_URL": "http://java-engine-worker:8081",
    "ELMOS_CONTROL_PLANE_BASE_URL": "http://control-plane:8080",
    "ELMOS_COMMERCIAL_API_URL": "http://commercial-api:8085",
    "ELMOS_WORKSPACE_SERVICE_URL": "http://workspace-service:8082",
    "ELMOS_REPOSITORY_WORKSPACE_BASE_URL": "http://control-plane:8080",
    "ELMOS_HOSTED_EXECUTION_ENABLED": "true",
    "ELMOS_LOCAL_RUNNER_ENABLED": "false",
}
WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED = {
    "ELMOS_DATABASE_SQL_PREFLIGHT_ENABLED": frozenset({"true", "false"}),
}
WEB_CONSOLE_FORBIDDEN_ENVIRONMENT_NORMALIZED = frozenset(
    {
        "ELMOSTRUSTEDSINGLETENANTORGANIZATIONID",
        "HTTPPROXY",
        "HTTPSPROXY",
        "ALLPROXY",
        "NOPROXY",
        "NODEUSEENVPROXY",
        "NODEEXTRAHEADERS",
        "NODEOPTIONS",
        "NODEPATH",
        "BASHENV",
        "ENV",
        "CLASSPATH",
        "JAVATOOLOPTIONS",
        "JDKJAVAOPTIONS",
        "JAVAOPTS",
        "MAVENOPTS",
        "GRADLEOPTS",
        "GITASKPASS",
        "GITSSHCOMMAND",
        "SSLCERTFILE",
        "SSLKEYLOGFILE",
    }
)
APPLICATION_MOUNT_SOURCE_NAMES = frozenset(
    {
        "worker_workspace",
        "worker_verifier_hmac",
        "worker_transformer_hmac",
        "worker_runtime_hmac",
        "application_engine_hmac",
        "worker_engine_replay",
        "web_resend_secret",
    }
)
APPLICATION_MOUNT_BINDINGS = {
    "worker_workspace": (("java-engine-worker", "/workspace/private-runner"),),
    "worker_verifier_hmac": (("java-engine-worker", "/run/secrets/elmos-verifier-hmac"),),
    "worker_transformer_hmac": (("java-engine-worker", "/run/secrets/elmos-transformer-hmac"),),
    "worker_runtime_hmac": (("java-engine-worker", "/run/secrets/elmos-runtime-hmac"),),
    "application_engine_hmac": (
        ("java-engine-worker", "/run/secrets/elmos-spring-engine-hmac"),
        ("web-console", "/run/secrets/elmos-spring-engine-hmac"),
    ),
    "worker_engine_replay": (
        ("java-engine-worker", "/var/lib/elmos/spring-engine-auth-replay"),
    ),
    "web_resend_secret": (("web-console", "/run/secrets/elmos/resend-api-key"),),
}
APPLICATION_DIRECTORY_MOUNT_SOURCES = frozenset(
    {"worker_workspace", "worker_engine_replay"}
)
WEB_RUNTIME_ATTESTATION_METHOD = "SANITIZED_DOCKER_INSPECT_MOUNT_OBJECTS_V3"
WORKER_IMAGE_ARTIFACT_ATTESTATION_METHOD = "OCI_IMAGE_CONTENT_EXTRACTION_V1"
DOCKER_ENVIRONMENT_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.DOTALL)
DANGEROUS_SPRING_WORKER_ENV_KEYS = frozenset(
    {
        "SPRING_APPLICATION_JSON",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JAVA_OPTS",
        "JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "JVM_OPTS",
        "JVM_OPTIONS",
        "CATALINA_OPTS",
        "SERVER_SERVLET_CONTEXT_PATH",
        "SERVER_SERVLET_PATH",
        "SPRING_MVC_SERVLET_PATH",
        "SPRING_CONFIG_LOCATION",
        "SPRING_CONFIG_ADDITIONAL_LOCATION",
        "SPRING_CONFIG_IMPORT",
        "SPRING_PROFILES_ACTIVE",
        "SPRING_PROFILES_INCLUDE",
        "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID",
    }
)

DIGEST_RE = re.compile(r"^sha256:(?!0{64}$)[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}$")
UTC_INSTANT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?Z$"
)
NON_SUCCESS = {
    "UNKNOWN",
    "INCONCLUSIVE",
    "NOT_RUN",
    "NOT_EVALUATED",
    "NOT_APPLICABLE",
    "UNSUPPORTED",
    "BLOCKED",
    "CHANGE_ME",
}
PLACEHOLDER_PREFIXES = (
    "CHANGE_ME",
    "PLACEHOLDER",
    "TODO",
    "TBD",
)

TOP_LEVEL_FIELDS = {
    "schema_version",
    "namespace",
    "receipt_id",
    "business_line",
    "route_id",
    "observed_at",
    "binding",
    "binding_digest",
    "principals",
    "evidence_index",
    "gates",
    "approvals",
    "design_partner_acceptances",
    "independent_review",
    "receipt_digest",
}
BINDING_FIELDS = {
    "deployed_revision",
    "launch_profile",
    "artifact",
    "environment",
}
CONTENT_REFERENCE_FIELDS = {"uri", "digest", "size_bytes", "media_type"}
EVIDENCE_REFERENCE_FIELDS = {*CONTENT_REFERENCE_FIELDS, "verification"}
PRINCIPAL_FIELDS = {"actor_id", "organization_id"}
ENVELOPE_FIELDS = {"algorithm", "key_id", "payload", "signature"}
COMMON_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "receipt_id",
    "binding_digest",
    "evidence_set_digest",
    "outcome",
    "synthetic",
    "unknowns",
    "not_run",
}
EXECUTION_PAYLOAD_FIELDS = {
    *COMMON_PAYLOAD_FIELDS,
    "gate_id",
    "evidence_uri",
    "evidence_digest",
    "evidence_size_bytes",
    "evidence_class",
}
VERIFICATION_PAYLOAD_FIELDS = {
    *EXECUTION_PAYLOAD_FIELDS,
    "execution_record_id",
    "execution_payload_digest",
}
APPROVAL_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "approval_scope"}
PARTNER_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "partner_organization_id"}
REVIEW_PAYLOAD_FIELDS = {*COMMON_PAYLOAD_FIELDS, "review_subject_digest"}
INDEX_PAYLOAD_FIELDS = {
    "record_id",
    "issued_at",
    "expires_at",
    "actor_id",
    "organization_id",
    "role",
    "receipt_id",
    "binding_digest",
    "index_id",
    "index_content_digest",
    "index_content_size_bytes",
    "outcome",
    "synthetic",
    "unknowns",
    "not_run",
}


class SpringLaunchEvidenceError(ValueError):
    """A Spring launch receipt failed closed."""


@dataclass(frozen=True)
class ContentObservation:
    uri: str
    digest: str
    size_bytes: int
    media_type: str
    path: Path
    content: bytes


@dataclass(frozen=True)
class ContainerRuntimeObservation:
    environment: dict[str, str]
    image_digest: str
    configured_image: str
    engine_secret_source: str
    backend_network: str
    mount_sources: dict[str, str]
    container_id: str
    container_name: str
    compose_project: str
    process_id: int
    sanitized_runtime_shape: dict[str, Any]


@dataclass(frozen=True)
class WebRuntimeObservation:
    image_digest: str
    configured_image: str
    engine_secret_source_digest: str
    backend_network: str
    mount_source_digests: dict[str, str]
    environment_names_digest: str
    configuration_digest: str
    raw_inspect_digest: str
    worker_inspect_digest: str
    worker_container_id: str
    application_mount_sources_digest: str


@dataclass(frozen=True)
class OpenedLocalFile:
    descriptor: int
    parent_descriptor: int
    filename: str
    path: Path


@dataclass(frozen=True)
class OpenedMountSource:
    descriptor: int
    parent_descriptor: int
    filename: str
    path: Path
    ancestor_descriptors: tuple[int, ...]


@dataclass(frozen=True)
class SecureFileSnapshot:
    content: bytes
    stat_result: os.stat_result


@dataclass(frozen=True)
class KeyMetadata:
    key_id: str
    actor_id: str
    organization_id: str
    role: str
    public_key_digest: str


@dataclass(frozen=True)
class LoadedTrust:
    store: TrustStore
    metadata: dict[str, KeyMetadata]


@dataclass(frozen=True)
class VerifiedEnvelope:
    payload: dict[str, Any]
    key_id: str
    actor_id: str
    organization_id: str
    role: str
    public_key_digest: str
    payload_digest: str
    envelope_digest: str
    issued_at: datetime


@dataclass(frozen=True)
class ControlledIndex:
    index_id: str
    content_digest: str
    entries: dict[str, dict[str, Any]]
    attestation: VerifiedEnvelope


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpringLaunchEvidenceError(f"{label} must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise SpringLaunchEvidenceError(
            f"{label} fields are invalid; missing={missing}, extra={extra}"
        )


def _identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or IDENTITY_RE.fullmatch(value) is None
        or _is_non_success_sentinel(value)
    ):
        raise SpringLaunchEvidenceError(
            f"{label} must be an exact non-placeholder identity"
        )
    return value


def _is_non_success_sentinel(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized in NON_SUCCESS:
        return True
    if any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES):
        return True
    return any(
        normalized.startswith(prefix + separator)
        for prefix in NON_SUCCESS
        for separator in ("_", "-", ":")
    )


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise SpringLaunchEvidenceError(
            f"{label} must be a non-zero sha256:<64 lowercase hex>"
        )
    return value


def _positive_size(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SpringLaunchEvidenceError(f"{label} must be a positive integer")
    return value


def _utc_instant(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_INSTANT_RE.fullmatch(value) is None:
        raise SpringLaunchEvidenceError(
            f"{label} must be an RFC3339 UTC instant ending in Z"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpringLaunchEvidenceError(f"{label} is not a valid RFC3339 instant") from exc
    return parsed.astimezone(timezone.utc)


def _reject_non_success(value: Any, label: str) -> None:
    if isinstance(value, str) and _is_non_success_sentinel(value):
        raise SpringLaunchEvidenceError(
            f"{label} contains non-success or placeholder sentinel {value}"
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_non_success(item, f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_non_success(item, f"{label}[{index}]")


def _approved_roots(values: Iterable[Path]) -> tuple[Path, ...]:
    candidates = list(values)
    if not candidates:
        raise SpringLaunchEvidenceError(
            "at least one explicit --evidence-root is required"
        )
    roots: list[Path] = []
    for candidate in candidates:
        supplied = candidate.expanduser()
        if supplied.is_symlink():
            raise SpringLaunchEvidenceError(
                f"evidence root must not be a symlink: {candidate}"
            )
        try:
            resolved = supplied.resolve(strict=True)
        except OSError as exc:
            raise SpringLaunchEvidenceError(
                f"evidence root does not exist: {candidate}"
            ) from exc
        if not resolved.is_dir():
            raise SpringLaunchEvidenceError(
                f"evidence root must be a directory: {resolved}"
            )
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _open_local_file(
    uri: Any, roots: tuple[Path, ...], label: str
) -> OpenedLocalFile:
    if not isinstance(uri, str) or not uri:
        raise SpringLaunchEvidenceError(f"{label} is required")
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise SpringLaunchEvidenceError(f"{label} must be an absolute local file URI")
    lexical = Path(os.path.abspath(Path(unquote(parsed.path))))
    containing_root = next((root for root in roots if _within(lexical, (root,))), None)
    if containing_root is None:
        raise SpringLaunchEvidenceError(
            f"{label} escapes approved evidence roots or is not a canonical path"
        )
    relative = lexical.relative_to(containing_root)
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise SpringLaunchEvidenceError(f"{label} has an invalid relative path")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    current_descriptor = -1
    file_descriptor = -1
    try:
        current_descriptor = os.open(containing_root, directory_flags)
        root_opened = os.fstat(current_descriptor)
        root_path = os.stat(containing_root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or _stat_identity(root_opened) != _stat_identity(root_path)
        ):
            raise SpringLaunchEvidenceError(
                f"{label} approved root changed while it was opened"
            )
        for part in relative.parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            opened = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_descriptor)
                raise SpringLaunchEvidenceError(
                    f"{label} contains a non-directory path component"
                )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        filename = relative.parts[-1]
        file_descriptor = os.open(filename, file_flags, dir_fd=current_descriptor)
        opened_file = os.fstat(file_descriptor)
        if not stat.S_ISREG(opened_file.st_mode):
            raise SpringLaunchEvidenceError(f"{label} must resolve to a regular file")
        return OpenedLocalFile(
            descriptor=file_descriptor,
            parent_descriptor=current_descriptor,
            filename=filename,
            path=containing_root / relative,
        )
    except (OSError, SpringLaunchEvidenceError) as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)
        if isinstance(exc, SpringLaunchEvidenceError):
            raise
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened beneath its approved root: {exc}"
        ) from exc


def _open_absolute_file(path: Path, label: str) -> OpenedLocalFile:
    """Open an absolute file by walking every directory with no-follow openat."""

    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError(f"{label} path must be absolute")
    components = supplied.parts[1:]
    if not components or any(part in {"", ".", ".."} for part in components):
        raise SpringLaunchEvidenceError(f"{label} path is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    current_descriptor = -1
    file_descriptor = -1
    try:
        current_descriptor = os.open(Path(supplied.anchor), directory_flags)
        for part in components[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            opened = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_descriptor)
                raise SpringLaunchEvidenceError(
                    f"{label} contains a non-directory path component"
                )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        filename = components[-1]
        file_descriptor = os.open(filename, file_flags, dir_fd=current_descriptor)
        if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
            raise SpringLaunchEvidenceError(f"{label} must be a regular file")
        return OpenedLocalFile(
            descriptor=file_descriptor,
            parent_descriptor=current_descriptor,
            filename=filename,
            path=supplied,
        )
    except (OSError, SpringLaunchEvidenceError) as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if current_descriptor >= 0:
            os.close(current_descriptor)
        if isinstance(exc, SpringLaunchEvidenceError):
            raise
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened without following links: {exc}"
        ) from exc


def _open_absolute_directory(path: Path, label: str) -> int:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError(f"{label} path must be absolute")
    components = supplied.parts[1:]
    if any(part in {"", ".", ".."} for part in components):
        raise SpringLaunchEvidenceError(f"{label} path is invalid")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(Path(supplied.anchor), flags)
        for part in components:
            next_descriptor = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened without following links: {exc}"
        ) from exc


def _read_secure_absolute_file(
    path: Path,
    *,
    max_bytes: int,
    label: str,
    allowed_modes: set[int] | None = None,
) -> SecureFileSnapshot:
    opened_file = _open_absolute_file(path, label)
    descriptor = opened_file.descriptor
    try:
        opened = os.fstat(descriptor)
        mode = stat.S_IMODE(opened.st_mode)
        if opened.st_uid != os.getuid():
            raise SpringLaunchEvidenceError(f"{label} must be owned by the current account")
        if opened.st_nlink != 1:
            raise SpringLaunchEvidenceError(f"{label} must have exactly one hard link")
        if allowed_modes is not None:
            if mode not in allowed_modes:
                rendered = ", ".join(f"{item:04o}" for item in sorted(allowed_modes))
                raise SpringLaunchEvidenceError(f"{label} mode must be one of {rendered}")
        elif mode & 0o022 or mode & 0o111 or not mode & 0o400:
            raise SpringLaunchEvidenceError(
                f"{label} must be owner-readable, non-executable, and not group/other writable"
            )
        if opened.st_size > max_bytes:
            raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise SpringLaunchEvidenceError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SpringLaunchEvidenceError(f"{label} changed while being read")
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_file.filename,
            dir_fd=opened_file.parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _stat_identity(completed) != _stat_identity(opened)
            or _stat_identity(path_after) != _stat_identity(opened)
        ):
            raise SpringLaunchEvidenceError(f"{label} changed while it was verified")
        return SecureFileSnapshot(b"".join(chunks), opened)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"{label} could not be read safely: {exc}") from exc
    finally:
        os.close(descriptor)
        os.close(opened_file.parent_descriptor)


def _snapshot_content_reference(
    value: Any,
    roots: tuple[Path, ...],
    label: str,
    *,
    max_bytes: int = MAX_CONTENT_BYTES,
    capture_content: bool = True,
) -> ContentObservation:
    reference = _object(value, label)
    _exact_fields(reference, CONTENT_REFERENCE_FIELDS, label)
    uri = reference.get("uri")
    digest = _digest(reference.get("digest"), f"{label}.digest")
    size = _positive_size(reference.get("size_bytes"), f"{label}.size_bytes")
    media_type = reference.get("media_type")
    if not isinstance(media_type, str) or not media_type or len(media_type) > 200:
        raise SpringLaunchEvidenceError(f"{label}.media_type is invalid")
    opened_local = _open_local_file(uri, roots, f"{label}.uri")
    descriptor = opened_local.descriptor
    chunks: list[bytes] = []
    digest_value = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise SpringLaunchEvidenceError(
                f"{label}.uri must resolve to a regular file descriptor"
            )
        if opened.st_size > max_bytes:
            raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise SpringLaunchEvidenceError(f"{label} changed while being read")
            digest_value.update(chunk)
            if capture_content:
                chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise SpringLaunchEvidenceError(f"{label} changed while being read")
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_local.filename,
            dir_fd=opened_local.parent_descriptor,
            follow_symlinks=False,
        )
    finally:
        os.close(descriptor)
        os.close(opened_local.parent_descriptor)
    if (
        _stat_identity(completed) != _stat_identity(opened)
        or _stat_identity(path_after) != _stat_identity(opened)
    ):
        raise SpringLaunchEvidenceError(f"{label} changed while it was verified")
    actual_digest = "sha256:" + digest_value.hexdigest()
    if size != opened.st_size:
        raise SpringLaunchEvidenceError(
            f"{label} byte count mismatch: expected {size}, observed {opened.st_size}"
        )
    if digest != actual_digest:
        raise SpringLaunchEvidenceError(
            f"{label} digest mismatch: expected {digest}, observed {actual_digest}"
        )
    return ContentObservation(
        uri=str(uri),
        digest=digest,
        size_bytes=size,
        media_type=media_type,
        path=opened_local.path,
        content=b"".join(chunks),
    )


def _immutable_uri(value: Any, digest: str, label: str) -> str:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise SpringLaunchEvidenceError(f"{label} must be a non-empty URI")
    parsed = urlparse(value)
    if parsed.scheme == "file":
        if (
            parsed.netloc not in {"", "localhost"}
            or not parsed.path.startswith("/")
            or parsed.query
            or parsed.fragment
        ):
            raise SpringLaunchEvidenceError(
                f"{label} file URI must be absolute and cannot carry query or fragment"
            )
        return value
    digest_hex = digest.removeprefix("sha256:")
    if parsed.scheme == "cas":
        if parsed.query or parsed.fragment:
            raise SpringLaunchEvidenceError(
                f"{label} CAS identity cannot carry query or fragment"
            )
        if f"{parsed.netloc}{parsed.path}".lstrip("/") != f"sha256/{digest_hex}":
            raise SpringLaunchEvidenceError(
                f"{label} CAS identity must equal the declared digest"
            )
        return value
    if parsed.scheme not in {"https", "s3", "gs", "az"} or not parsed.netloc:
        raise SpringLaunchEvidenceError(
            f"{label} must use file, cas, https, s3, gs, or az"
        )
    decoded_path = unquote(parsed.path)
    if (
        parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in decoded_path)
    ):
        raise SpringLaunchEvidenceError(
            f"{label} remote URI contains credentials, fragment, whitespace, or control characters"
        )
    query: dict[str, list[str]] = {}
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        query.setdefault(key.lower(), []).extend(values)
    digest_pins = [
        item
        for key in ("sha256", "digest")
        for item in query.get(key, [])
    ]
    if any(not item for item in digest_pins):
        raise SpringLaunchEvidenceError(
            f"{label} digest query pin cannot be empty"
        )
    if digest_pins and any(
        item not in {digest_hex, f"sha256:{digest_hex}"} for item in digest_pins
    ):
        raise SpringLaunchEvidenceError(
            f"{label} digest query pin must equal the declared content digest"
        )
    scheme_version_keys = {
        "https": set(),
        "s3": {"versionid"},
        "gs": {"generation"},
        "az": {"versionid", "snapshot"},
    }
    version_values = [
        item
        for key in scheme_version_keys[parsed.scheme]
        for item in query.get(key, [])
    ]
    valid_version = re.compile(r"^[A-Za-z0-9._~:+/=\-]{1,512}$")
    if any(valid_version.fullmatch(item) is None for item in version_values):
        raise SpringLaunchEvidenceError(
            f"{label} version pin contains whitespace, control characters, or invalid length"
        )
    if any(
        item.lower() in {"latest", "current", "head", "null"}
        or _is_non_success_sentinel(item)
        for item in version_values
    ):
        raise SpringLaunchEvidenceError(
            f"{label} version pin cannot use a mutable or placeholder value"
        )
    if parsed.scheme == "gs" and any(
        re.fullmatch(r"[1-9][0-9]{0,30}", item) is None for item in version_values
    ):
        raise SpringLaunchEvidenceError(
            f"{label} gs generation pin must be a positive decimal integer"
        )
    version_pinned = any(
        item for item in version_values
    )
    path_digests = re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", parsed.path)
    if path_digests and any(item != digest_hex for item in path_digests):
        raise SpringLaunchEvidenceError(
            f"{label} digest path pin must equal the declared content digest"
        )
    if not version_pinned and not digest_pins and digest_hex not in path_digests:
        raise SpringLaunchEvidenceError(
            f"{label} remote URI must carry a version/generation/snapshot/digest pin"
        )
    return value


def _load_strict_json_bytes(content: bytes, label: str) -> Any:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate object key {key!r}")
            result[key] = item
        return result

    try:
        value = json.loads(
            content.decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {constant}")
            ),
            object_pairs_hook=strict_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SpringLaunchEvidenceError(f"{label} must be strict UTF-8 JSON: {exc}") from exc
    return value


def _load_json_bytes(content: bytes, label: str) -> dict[str, Any]:
    return _object(_load_strict_json_bytes(content, label), label)


def _canonical_json_document(content: bytes, label: str) -> dict[str, Any]:
    value = _load_json_bytes(content, label)
    if content != canonical_bytes(value):
        raise SpringLaunchEvidenceError(
            f"{label} bytes must be canonical JSON (sorted keys, UTF-8, no whitespace)"
        )
    return value


def _validate_trust_store_path(path: Path, evidence_roots: tuple[Path, ...]) -> Path:
    supplied = path.expanduser()
    if not supplied.is_absolute():
        raise SpringLaunchEvidenceError("Spring launch trust store path must be absolute")
    try:
        path_stat = os.stat(supplied, follow_symlinks=False)
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"Spring launch trust store is unavailable: {exc}"
        ) from exc
    if stat.S_ISLNK(path_stat.st_mode) or supplied != resolved:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store path must be canonical and contain no symlink"
        )
    if not stat.S_ISREG(path_stat.st_mode):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be a regular file"
        )
    if path_stat.st_uid != os.getuid():
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be owned by the current account"
        )
    if stat.S_IMODE(path_stat.st_mode) not in {0o400, 0o600}:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must use owner-only mode 0400 or 0600"
        )
    if path_stat.st_nlink != 1:
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must have exactly one hard link"
        )
    if evidence_roots and _within(resolved, evidence_roots):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store must be outside all evidence roots"
        )
    return resolved


@lru_cache(maxsize=256)
def _canonical_ed25519_spki(public_key_bytes: bytes) -> bytes:
    try:
        completed = subprocess.run(
            ["openssl", "pkey", "-pubin", "-outform", "DER"],
            input=public_key_bytes,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"OpenSSL public-key decode failed: {exc}") from exc
    der = completed.stdout
    if (
        completed.returncode != 0
        or len(der) != len(ED25519_SPKI_DER_PREFIX) + 32
        or not der.startswith(ED25519_SPKI_DER_PREFIX)
    ):
        raise ValueError("public key is not canonical Ed25519 SubjectPublicKeyInfo")
    return der


def _ed25519_spki_digest(public_key_bytes: bytes, label: str) -> str:
    """Return a representation-independent Ed25519 SPKI fingerprint."""

    try:
        der = _canonical_ed25519_spki(public_key_bytes)
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} must be an Ed25519 SubjectPublicKeyInfo public key: {exc}"
        ) from exc
    return "sha256:" + hashlib.sha256(der).hexdigest()


def _load_trust(
    path: Path, *, evidence_roots: tuple[Path, ...] = ()
) -> LoadedTrust:
    canonical_path = _validate_trust_store_path(path, evidence_roots)
    snapshot = _read_secure_absolute_file(
        canonical_path,
        max_bytes=1024 * 1024,
        label="Spring launch trust store",
        allowed_modes={0o400, 0o600},
    )
    document = _load_json_bytes(snapshot.content, "Spring launch trust store")
    trust = _object(document, "trust store")
    _exact_fields(
        trust,
        {"schema_version", "namespace", "keys", "revoked_record_ids"},
        "trust store",
    )
    if (
        type(trust.get("schema_version")) is not int
        or trust.get("schema_version") != 1
        or trust.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("trust store identity is invalid")
    records = trust.get("keys")
    if not isinstance(records, list) or not records:
        raise SpringLaunchEvidenceError("trust store keys must be a non-empty array")
    revoked_ids = trust.get("revoked_record_ids")
    if (
        not isinstance(revoked_ids, list)
        or len(set(map(str, revoked_ids))) != len(revoked_ids)
        or any(not isinstance(item, str) or not item for item in revoked_ids)
    ):
        raise SpringLaunchEvidenceError("trust store revoked_record_ids is invalid")
    metadata: dict[str, KeyMetadata] = {}
    trusted_keys: dict[str, TrustedKey] = {}
    raw_public_key_digests: dict[str, str] = {}
    key_fields = {
        "key_id",
        "actor_id",
        "organization_id",
        "roles",
        "public_key_path",
        "not_before",
        "not_after",
        "revoked",
    }
    for index, raw in enumerate(records):
        item = _object(raw, f"trust store key {index}")
        _exact_fields(item, key_fields, f"trust store key {index}")
        key_id = _identity(item.get("key_id"), f"trust store key {index}.key_id")
        if key_id in metadata:
            raise SpringLaunchEvidenceError(f"duplicate trust key identity: {key_id}")
        actor = _identity(item.get("actor_id"), f"trust store key {key_id}.actor_id")
        organization = _identity(
            item.get("organization_id"), f"trust store key {key_id}.organization_id"
        )
        roles = item.get("roles")
        if not isinstance(roles, list) or len(roles) != 1 or roles[0] not in ALLOWED_ROLES:
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id} must have exactly one allowed role"
            )
        not_before = _utc_instant(
            item.get("not_before"), f"trust store key {key_id}.not_before"
        )
        not_after = _utc_instant(
            item.get("not_after"), f"trust store key {key_id}.not_after"
        )
        if not_after <= not_before:
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id} validity window is invalid"
            )
        if not isinstance(item.get("revoked"), bool):
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id}.revoked must be boolean"
            )
        relative_key = item.get("public_key_path")
        if (
            not isinstance(relative_key, str)
            or not relative_key
            or Path(relative_key).is_absolute()
            or ".." in Path(relative_key).parts
        ):
            raise SpringLaunchEvidenceError(
                f"trust store key {key_id}.public_key_path is invalid"
            )
        key_path = canonical_path.parent / relative_key
        key_snapshot = _read_secure_absolute_file(
            key_path,
            max_bytes=64 * 1024,
            label=f"trust store key {key_id}",
        )
        public_digest = _ed25519_spki_digest(
            key_snapshot.content,
            f"trust store key {key_id}.public_key_path",
        )
        raw_public_key_digests[key_id] = (
            "sha256:" + hashlib.sha256(key_snapshot.content).hexdigest()
        )
        if item["revoked"] is False:
            trusted_keys[key_id] = TrustedKey(
                key_id=key_id,
                roles=frozenset(roles),
                public_key_path=key_path,
                public_key_bytes=key_snapshot.content,
                public_key_digest=raw_public_key_digests[key_id],
                not_before=not_before,
                not_after=not_after,
            )
        metadata[key_id] = KeyMetadata(
            key_id=key_id,
            actor_id=actor,
            organization_id=organization,
            role=roles[0],
            public_key_digest=public_digest,
        )
    after_load = os.stat(canonical_path, follow_symlinks=False)
    if _stat_identity(after_load) != _stat_identity(snapshot.stat_result):
        raise SpringLaunchEvidenceError(
            "Spring launch trust store changed while its keys were loaded"
        )
    store = TrustStore(
        path=canonical_path,
        keys=trusted_keys,
        revoked_record_ids=frozenset(revoked_ids),
        digest=canonical_digest(
            {
                "trust_store": "sha256:" + hashlib.sha256(snapshot.content).hexdigest(),
                "public_keys": dict(sorted(raw_public_key_digests.items())),
            }
        ),
    )
    return LoadedTrust(store=store, metadata=metadata)


def _verify_envelope(
    loaded: LoadedTrust,
    value: Any,
    *,
    role: str,
    expected_fields: set[str],
    bindings: dict[str, Any],
    now: datetime,
    expected_principal: dict[str, str] | None = None,
) -> VerifiedEnvelope:
    envelope = _object(value, f"{role} envelope")
    _exact_fields(envelope, ENVELOPE_FIELDS, f"{role} envelope")
    if envelope.get("algorithm") != "ed25519":
        raise SpringLaunchEvidenceError(
            f"{role} envelope algorithm must be exactly ed25519"
        )
    key_id = envelope.get("key_id")
    if not isinstance(key_id, str) or key_id not in loaded.metadata:
        raise SpringLaunchEvidenceError(f"{role} signing key is unknown")
    metadata = loaded.metadata[key_id]
    if metadata.role != role:
        raise SpringLaunchEvidenceError(
            f"{role} signing key must be dedicated to exactly that role"
        )
    if expected_principal is not None and (
        metadata.actor_id != expected_principal["actor_id"]
        or metadata.organization_id != expected_principal["organization_id"]
    ):
        raise SpringLaunchEvidenceError(
            f"{role} signer does not match its declared principal"
        )
    payload = _object(envelope.get("payload"), f"{role} payload")
    _exact_fields(payload, expected_fields, f"{role} payload")
    _identity(payload.get("record_id"), f"{role} payload.record_id")
    issued_at = _utc_instant(payload.get("issued_at"), f"{role} payload.issued_at")
    _utc_instant(payload.get("expires_at"), f"{role} payload.expires_at")
    if payload.get("actor_id") != metadata.actor_id:
        raise SpringLaunchEvidenceError(f"{role} signed actor does not match trust store")
    if payload.get("organization_id") != metadata.organization_id:
        raise SpringLaunchEvidenceError(
            f"{role} signed organization does not match trust store"
        )
    if payload.get("role") != role:
        raise SpringLaunchEvidenceError(f"{role} payload role binding is invalid")
    if payload.get("synthetic") is not False:
        raise SpringLaunchEvidenceError(f"{role} payload.synthetic must be false")
    for field in ("unknowns", "not_run"):
        if not isinstance(payload.get(field), list) or payload[field]:
            raise SpringLaunchEvidenceError(
                f"{role} payload.{field} must be an exact empty array"
            )
    for field in ("evidence_size_bytes", "index_content_size_bytes"):
        if field in payload:
            _positive_size(payload[field], f"{role} payload.{field}")
    _reject_non_success(payload, f"{role} payload")
    try:
        decoded_signature = decode_signature(envelope.get("signature"))
    except (TypeError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"{role} signature is not valid base64"
        ) from exc
    if len(decoded_signature) != ED25519_SIGNATURE_BYTES:
        raise SpringLaunchEvidenceError(
            f"{role} signature must decode to exactly {ED25519_SIGNATURE_BYTES} bytes"
        )
    try:
        receipt = loaded.store.verify_envelope(
            envelope,
            required_role=role,
            bindings=bindings,
            now=now,
        )
    except (OSError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"{role} signature verification failed: {exc}"
        ) from exc
    return VerifiedEnvelope(
        payload=payload,
        key_id=key_id,
        actor_id=metadata.actor_id,
        organization_id=metadata.organization_id,
        role=role,
        public_key_digest=metadata.public_key_digest,
        payload_digest=receipt["payload_digest"],
        envelope_digest=canonical_digest(envelope),
        issued_at=issued_at,
    )


def _principal(value: Any, label: str) -> dict[str, str]:
    principal = _object(value, label)
    _exact_fields(principal, PRINCIPAL_FIELDS, label)
    return {
        "actor_id": _identity(principal.get("actor_id"), f"{label}.actor_id"),
        "organization_id": _identity(
            principal.get("organization_id"), f"{label}.organization_id"
        ),
    }


def _expected_revision(value: str | None, repo_root: Path) -> str:
    if value is not None:
        if REVISION_RE.fullmatch(value) is None:
            raise SpringLaunchEvidenceError(
                "expected revision must be 40 lowercase hexadecimal characters"
            )
        return value
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or REVISION_RE.fullmatch(revision) is None:
        raise SpringLaunchEvidenceError("could not resolve the current repository HEAD")
    return revision


def _committed_file_bytes(
    repo_root: Path,
    revision: str,
    path: Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    """Read one exact blob from Git without trusting working-tree bytes."""

    try:
        canonical_root = repo_root.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"{label} repository root is unavailable") from exc
    supplied = path if path.is_absolute() else canonical_root / path
    try:
        relative = supplied.relative_to(canonical_root)
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} must be inside the repository"
        ) from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise SpringLaunchEvidenceError(f"{label} repository path is invalid")
    object_name = f"{revision}:{relative.as_posix()}"
    try:
        size_result = subprocess.run(
            ["git", "cat-file", "-s", object_name],
            cwd=canonical_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob size could not be resolved"
        ) from exc
    try:
        size = int(size_result.stdout.strip())
    except ValueError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} is not a blob at the expected revision"
        ) from exc
    if size_result.returncode != 0 or size < 0 or size > max_bytes:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob is unavailable or exceeds the byte budget"
        )
    try:
        blob_result = subprocess.run(
            ["git", "cat-file", "blob", object_name],
            cwd=canonical_root,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob could not be read"
        ) from exc
    if blob_result.returncode != 0 or len(blob_result.stdout) != size:
        raise SpringLaunchEvidenceError(
            f"{label} committed blob changed or could not be read exactly"
        )
    return blob_result.stdout


def _normalized_environment_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name).upper()


_DANGEROUS_SPRING_WORKER_ENV_NORMALIZED = frozenset(
    _normalized_environment_name(name)
    for name in DANGEROUS_SPRING_WORKER_ENV_KEYS
)
_SPRING_WORKER_ENV_CANONICAL_BY_NORMALIZED = {
    _normalized_environment_name(name): name
    for name in (
        *SPRING_WORKER_CONFIGURATION_ENV_KEYS,
        *SPRING_WORKER_ALLOWED_EXPLICIT_EMPTY_ENVIRONMENT,
        *SPRING_WORKER_EXECUTION_ENVIRONMENT,
    )
}


def _dangerous_spring_worker_environment_name(name: str) -> bool:
    normalized = _normalized_environment_name(name)
    return (
        normalized in _DANGEROUS_SPRING_WORKER_ENV_NORMALIZED
        or normalized.startswith("SPRING")
        or normalized.startswith("SERVER")
        or normalized.startswith("MANAGEMENT")
        or normalized.startswith("ELMOSWORKER")
        or normalized.startswith("LD")
        or normalized.startswith("JVM")
        or normalized in {
            "CLASSPATH",
            "BASHENV",
            "ENV",
            "MAVENOPTS",
            "MAVENARGS",
            "MAVENCMDLINEARGS",
            "GRADLEOPTS",
            "GRADLEUSERHOME",
        }
    )


def normalized_spring_worker_environment(
    environment: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Return every supported key with an explicit presence/value record."""

    values: dict[str, dict[str, Any]] = {}
    for name in SPRING_WORKER_EFFECTIVE_ENV_KEYS:
        if name not in environment:
            values[name] = {"present": False}
            continue
        raw = environment[name]
        if not isinstance(raw, str):
            raise SpringLaunchEvidenceError(
                f"effective Spring worker environment value {name} must be a string"
            )
        values[name] = {"present": True, "value": raw}
    return values


def expected_spring_worker_environment(
    spring_environment: Mapping[str, str],
) -> dict[str, str]:
    """Build the exact worker environment expected from controlled deployment inputs.

    ``spring_environment`` is the already validated effective Spring/Compose
    input mapping.  Fixed values come from the pinned worker image and
    production Compose contract; dynamic values retain their validated host
    values.  Unsupported configuration keys remain absent.  The eight
    process-level overrides deliberately cleared by Compose are included as
    exact empty assignments by a separate allowlist.
    """

    expected = {
        **SPRING_WORKER_FIXED_ENVIRONMENT,
        **SPRING_WORKER_EXECUTION_ENVIRONMENT,
    }
    for name in SPRING_WORKER_DYNAMIC_ENV_KEYS:
        if name not in spring_environment:
            raise SpringLaunchEvidenceError(
                f"expected Spring worker environment value {name} is required"
            )
        raw = spring_environment[name]
        if not isinstance(raw, str):
            raise SpringLaunchEvidenceError(
                f"expected Spring worker environment value {name} must be a string"
            )
        expected[name] = raw
    expected.update(
        {
            name: ""
            for name in SPRING_WORKER_ALLOWED_EXPLICIT_EMPTY_ENVIRONMENT
        }
    )
    return expected


def expected_spring_worker_configuration_digest(
    spring_environment: Mapping[str, str],
) -> str:
    """Return the independently derived expected worker environment digest."""

    return spring_worker_configuration_digest(
        expected_spring_worker_environment(spring_environment)
    )


def spring_worker_configuration_digest(environment: Mapping[str, str]) -> str:
    """Digest normalized, non-secret configuration for ``java-engine-worker``.

    This digest intentionally has a different contract from the host-side
    ``configuration_digest``.  It proves which effective container values were
    observed; it is not, and must never be presented as, the combined digest of
    the host Spring environment and Compose environment-file bytes.
    """

    values = normalized_spring_worker_environment(environment)
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-effective-worker-environment-v2",
            "service": "java-engine-worker",
            "values": values,
        }
    )


def expected_web_console_environment(
    compose_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Derive the exact web environment from env-file names plus controlled overrides.

    The returned mapping is for in-memory comparison only and may contain the
    supplied application secret values.  Callers must never serialize it into
    evidence.  The collector serializes only names and the required non-secret
    subset.
    """

    expected: dict[str, str] = {}
    for name, value in (compose_environment or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise SpringLaunchEvidenceError(
                "compose web-console environment names and values must be strings"
            )
        normalized = _normalized_environment_name(name)
        if (
            normalized.startswith("ELMOSSPRING")
            or normalized.startswith("SPRING")
            or normalized.startswith("SERVER")
            or normalized.startswith("MANAGEMENT")
            or normalized == "ELMOSTRUSTEDSINGLETENANTORGANIZATIONID"
            or normalized in WEB_CONSOLE_FORBIDDEN_ENVIRONMENT_NORMALIZED
            or normalized.startswith("LD")
            or normalized.startswith("DYLD")
        ):
            raise SpringLaunchEvidenceError(
                f"application Compose env file must not declare Spring or process override {name}"
            )
        expected[name] = value
    for name, allowed in WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED.items():
        value = expected.get(name, "false")
        if value not in allowed:
            raise SpringLaunchEvidenceError(
                f"expected web-console dynamic value {name} is invalid"
            )
        expected[name] = value
    expected.update(WEB_CONSOLE_CONFIGURATION_ENVIRONMENT)
    _validate_web_console_environment(
        expected, label="expected controlled web-console environment"
    )
    return expected


def expected_web_console_environment_names(
    compose_environment: Mapping[str, str],
) -> tuple[str, ...]:
    """Return the independently derived exact Docker environment-name inventory."""

    return tuple(sorted(expected_web_console_environment(compose_environment)))


def application_environment_commitment_digest(
    environment: Mapping[str, str],
) -> str:
    """Commit to app env shape without creating an offline secret-value oracle.

    Every exact key and whether its value is empty is bound.  Only the one
    explicitly non-secret feature flag used by the Spring deployment contract
    contributes its value.  Database, OIDC, provider, API and session secret
    values are never copied or hashed into this portable receipt commitment.
    """

    variables: dict[str, dict[str, Any]] = {}
    normalized_names: dict[str, str] = {}
    for name in sorted(environment):
        value = environment[name]
        if (
            not isinstance(name, str)
            or not isinstance(value, str)
            or DOCKER_ENVIRONMENT_ASSIGNMENT.fullmatch(f"{name}=") is None
        ):
            raise SpringLaunchEvidenceError(
                "application environment names and values must be exact strings"
            )
        normalized = _normalized_environment_name(name)
        prior = normalized_names.setdefault(normalized, name)
        if prior != name:
            raise SpringLaunchEvidenceError(
                f"application environment contains relaxed-binding aliases {prior} and {name}"
            )
        record: dict[str, Any] = {"present": True, "empty": value == ""}
        if name in WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED:
            if value not in WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED[name]:
                raise SpringLaunchEvidenceError(
                    f"application environment non-secret value {name} is invalid"
                )
            record["non_secret_value"] = value
        variables[name] = record
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-application-environment-redacted-commitment-v1",
            "variables": variables,
        }
    )


def web_console_configuration_digest(environment: Mapping[str, str]) -> str:
    """Digest only required non-secret web-console configuration values.

    The full web container inherits application secrets.  Those values must
    never be copied into launch evidence or hashed into a reusable offline
    dictionary oracle.  The separate environment-name digest binds the exact
    key inventory, while the launch configuration binds the source env-file
    bytes out of band.
    """

    values: dict[str, dict[str, Any]] = {}
    for name in sorted(
        {*WEB_CONSOLE_CONFIGURATION_ENVIRONMENT, *WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED}
    ):
        if name not in environment:
            values[name] = {"present": False}
            continue
        value = environment[name]
        if not isinstance(value, str):
            raise SpringLaunchEvidenceError(
                f"web-console environment value {name} must be a string"
            )
        values[name] = {"present": True, "value": value}
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-effective-web-console-environment-v1",
            "service": "web-console",
            "values": values,
        }
    )


def web_console_environment_names_digest(names: Iterable[str]) -> str:
    """Digest an exact, alias-free web-console environment-name inventory."""

    ordered: list[str] = []
    normalized: dict[str, str] = {}
    for raw in names:
        if not isinstance(raw, str) or DOCKER_ENVIRONMENT_ASSIGNMENT.fullmatch(
            f"{raw}="
        ) is None:
            raise SpringLaunchEvidenceError(
                "web-console environment names must be exact Docker variable names"
            )
        if raw in ordered:
            raise SpringLaunchEvidenceError(
                f"web-console environment names contain duplicate key {raw}"
            )
        normalized_name = _normalized_environment_name(raw)
        prior = normalized.setdefault(normalized_name, raw)
        if prior != raw:
            raise SpringLaunchEvidenceError(
                f"web-console environment names contain relaxed-binding aliases {prior} and {raw}"
            )
        ordered.append(raw)
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-web-console-environment-names-v1",
            "names": sorted(ordered),
        }
    )


MOUNT_OBJECT_IDENTITY_FIELDS = frozenset(
    {
        "device",
        "inode",
        "object_type",
        "size_bytes",
        "mode",
        "uid",
        "gid",
        "link_count",
        "ctime_ns",
    }
)


def _mount_source_path_digest(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def _mount_object_identity(value: os.stat_result) -> dict[str, Any]:
    if stat.S_ISREG(value.st_mode):
        object_type = "REGULAR_FILE"
    elif stat.S_ISDIR(value.st_mode):
        object_type = "DIRECTORY"
    else:
        raise SpringLaunchEvidenceError(
            "application mount source must be a regular file or directory"
        )
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "object_type": object_type,
        "size_bytes": value.st_size,
        "mode": stat.S_IMODE(value.st_mode),
        "uid": value.st_uid,
        "gid": value.st_gid,
        "link_count": value.st_nlink,
        "ctime_ns": value.st_ctime_ns,
    }


def _validated_mount_object_identity(value: Any, label: str) -> dict[str, Any]:
    identity = _object(value, label)
    _exact_fields(identity, MOUNT_OBJECT_IDENTITY_FIELDS, label)
    for name in MOUNT_OBJECT_IDENTITY_FIELDS - {"object_type"}:
        item = identity.get(name)
        if type(item) is not int or item < 0:
            raise SpringLaunchEvidenceError(f"{label}.{name} must be a non-negative integer")
    if identity.get("device") == 0 or identity.get("inode") == 0:
        raise SpringLaunchEvidenceError(
            f"{label} must bind a non-zero filesystem device and inode"
        )
    if identity.get("object_type") not in {"REGULAR_FILE", "DIRECTORY"}:
        raise SpringLaunchEvidenceError(
            f"{label}.object_type must be REGULAR_FILE or DIRECTORY"
        )
    if identity.get("link_count") < 1:
        raise SpringLaunchEvidenceError(f"{label}.link_count must be positive")
    if identity.get("mode") > 0o7777:
        raise SpringLaunchEvidenceError(f"{label}.mode is invalid")
    return dict(identity)


def _validate_application_mount_object_contract(
    semantic_name: str,
    identity: Mapping[str, Any],
    parent_identity: Mapping[str, Any],
    ancestor_identities: Iterable[Mapping[str, Any]],
    *,
    expected_uid: int,
    expected_gid: int,
    label: str,
) -> None:
    if (
        type(expected_uid) is not int
        or expected_uid < 0
        or type(expected_gid) is not int
        or expected_gid < 0
    ):
        raise SpringLaunchEvidenceError("expected mount UID/GID must be non-negative integers")
    ancestors = list(ancestor_identities)
    if not ancestors or ancestors[-1] != parent_identity:
        raise SpringLaunchEvidenceError(
            f"{label} ancestry must end at the captured immediate parent"
        )
    seen_ancestors: set[tuple[int, int]] = set()
    for index, ancestor in enumerate(ancestors):
        inode_key = (ancestor["device"], ancestor["inode"])
        if inode_key in seen_ancestors:
            raise SpringLaunchEvidenceError(f"{label} ancestry contains a cycle")
        seen_ancestors.add(inode_key)
        writable_without_sticky = bool(ancestor["mode"] & 0o022) and not bool(
            ancestor["mode"] & stat.S_ISVTX
        )
        if (
            ancestor["object_type"] != "DIRECTORY"
            or writable_without_sticky
            or ancestor["uid"] not in {0, expected_uid}
        ):
            raise SpringLaunchEvidenceError(
                f"{label} ancestor {index} must be root/deploy-owned and not unsafely group/other writable"
            )
    expected_type = (
        "DIRECTORY"
        if semantic_name in APPLICATION_DIRECTORY_MOUNT_SOURCES
        else "REGULAR_FILE"
    )
    if expected_type == "REGULAR_FILE" and (
        parent_identity["object_type"] != "DIRECTORY"
        or parent_identity["mode"] != 0o700
        or parent_identity["uid"] != expected_uid
        or parent_identity["gid"] != expected_gid
    ):
        raise SpringLaunchEvidenceError(
            f"{label} immediate parent must be a 0700 directory owned by UID/GID {expected_uid}:{expected_gid}"
        )
    if identity["object_type"] != expected_type:
        raise SpringLaunchEvidenceError(
            f"{label} must bind a {expected_type.lower()}"
        )
    if identity["uid"] != expected_uid or identity["gid"] != expected_gid:
        raise SpringLaunchEvidenceError(
            f"{label} must be owned by UID/GID {expected_uid}:{expected_gid}"
        )
    if expected_type == "DIRECTORY":
        if identity["mode"] != 0o700:
            raise SpringLaunchEvidenceError(f"{label} directory mode must be 0700")
        return
    if identity["mode"] not in {0o400, 0o600}:
        raise SpringLaunchEvidenceError(f"{label} secret mode must be 0400 or 0600")
    if identity["link_count"] != 1:
        raise SpringLaunchEvidenceError(f"{label} secret must have exactly one hard link")
    if not 32 <= identity["size_bytes"] <= 4096:
        raise SpringLaunchEvidenceError(
            f"{label} secret size must be 32-4096 bytes"
        )


def _open_absolute_mount_source(path: Path, label: str) -> OpenedMountSource:
    """Open a file or directory by walking every component without symlinks."""

    supplied = path.expanduser()
    if not supplied.is_absolute() or supplied == Path("/"):
        raise SpringLaunchEvidenceError(f"{label} path must be absolute and non-root")
    if supplied != Path(os.path.normpath(supplied)):
        raise SpringLaunchEvidenceError(f"{label} path must be normalized")
    components = supplied.parts[1:]
    if not components or any(part in {"", ".", ".."} for part in components):
        raise SpringLaunchEvidenceError(f"{label} path is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    object_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    ancestor_descriptors: list[int] = []
    object_descriptor = -1
    try:
        current_descriptor = os.open(Path(supplied.anchor), directory_flags)
        ancestor_descriptors.append(current_descriptor)
        for part in components[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current_descriptor)
            opened = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_descriptor)
                raise SpringLaunchEvidenceError(
                    f"{label} contains a non-directory path component"
                )
            current_descriptor = next_descriptor
            ancestor_descriptors.append(current_descriptor)
        filename = components[-1]
        object_descriptor = os.open(filename, object_flags, dir_fd=current_descriptor)
        opened = os.fstat(object_descriptor)
        if not (stat.S_ISREG(opened.st_mode) or stat.S_ISDIR(opened.st_mode)):
            raise SpringLaunchEvidenceError(
                f"{label} must be a regular file or directory"
            )
        return OpenedMountSource(
            descriptor=object_descriptor,
            parent_descriptor=current_descriptor,
            filename=filename,
            path=supplied,
            ancestor_descriptors=tuple(ancestor_descriptors),
        )
    except (OSError, SpringLaunchEvidenceError) as exc:
        if object_descriptor >= 0:
            os.close(object_descriptor)
        for descriptor in reversed(ancestor_descriptors):
            os.close(descriptor)
        if isinstance(exc, SpringLaunchEvidenceError):
            raise
        raise SpringLaunchEvidenceError(
            f"{label} could not be opened without following links: {exc}"
        ) from exc


def _snapshot_mount_source_identity(source: str, label: str) -> dict[str, Any]:
    opened_source = _open_absolute_mount_source(Path(source), label)
    try:
        before = os.fstat(opened_source.descriptor)
        ancestor_before = [
            os.fstat(descriptor)
            for descriptor in opened_source.ancestor_descriptors
        ]
        path_value = os.stat(
            opened_source.filename,
            dir_fd=opened_source.parent_descriptor,
            follow_symlinks=False,
        )
        after = os.fstat(opened_source.descriptor)
        ancestor_after = [
            os.fstat(descriptor)
            for descriptor in opened_source.ancestor_descriptors
        ]
        ancestor_path_after = [
            os.stat(opened_source.path.anchor, follow_symlinks=False)
        ]
        for index, part in enumerate(opened_source.path.parts[1:-1], start=1):
            ancestor_path_after.append(
                os.stat(
                    part,
                    dir_fd=opened_source.ancestor_descriptors[index - 1],
                    follow_symlinks=False,
                )
            )
        if (
            _stat_identity(before) != _stat_identity(path_value)
            or _stat_identity(before) != _stat_identity(after)
            or any(
                _stat_identity(left) != _stat_identity(right)
                for left, right in zip(
                    ancestor_before, ancestor_after, strict=True
                )
            )
            or any(
                _stat_identity(left) != _stat_identity(right)
                for left, right in zip(
                    ancestor_before, ancestor_path_after, strict=True
                )
            )
        ):
            raise SpringLaunchEvidenceError(
                f"{label} changed while its object identity was captured"
            )
        return {
            "object_identity": _mount_object_identity(before),
            "parent_identity": _mount_object_identity(ancestor_before[-1]),
            "ancestor_identities": [
                _mount_object_identity(value) for value in ancestor_before
            ],
        }
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} object identity could not be captured safely: {exc}"
        ) from exc
    finally:
        os.close(opened_source.descriptor)
        for descriptor in reversed(opened_source.ancestor_descriptors):
            os.close(descriptor)


def _application_mount_source_identities_digest(
    identities: Mapping[str, Mapping[str, Any]],
) -> str:
    if set(identities) != APPLICATION_MOUNT_SOURCE_NAMES:
        raise SpringLaunchEvidenceError(
            "application mount source identities must contain the exact controlled set"
        )
    normalized: dict[str, dict[str, Any]] = {}
    for name in sorted(APPLICATION_MOUNT_SOURCE_NAMES):
        record = _object(
            identities.get(name), f"application mount source identity {name}"
        )
        _exact_fields(
            record,
            {
                "source_path_digest",
                "object_identity",
                "parent_identity",
                "ancestor_identities",
            },
            f"application mount source identity {name}",
        )
        object_identity = _validated_mount_object_identity(
            record.get("object_identity"),
            f"application mount source identity {name}.object_identity",
        )
        parent_identity = _validated_mount_object_identity(
            record.get("parent_identity"),
            f"application mount source identity {name}.parent_identity",
        )
        raw_ancestors = record.get("ancestor_identities")
        if not isinstance(raw_ancestors, list) or not raw_ancestors:
            raise SpringLaunchEvidenceError(
                f"application mount source identity {name}.ancestor_identities must be non-empty"
            )
        ancestor_identities = [
            _validated_mount_object_identity(
                item,
                f"application mount source identity {name}.ancestor_identities[{index}]",
            )
            for index, item in enumerate(raw_ancestors)
        ]
        if ancestor_identities[-1] != parent_identity:
            raise SpringLaunchEvidenceError(
                f"application mount source identity {name} parent does not match its ancestry"
            )
        # Writable workspace/replay directories legitimately change size,
        # link count and ctime as jobs execute.  Their stable inode/security
        # fields are bound here and their lifecycle is separately bound by the
        # signed deployment_id.  Secret files retain every change-sensitive
        # field so in-place rotation changes the commitment.
        digest_identity = (
            {
                field: object_identity[field]
                for field in (
                    "device",
                    "inode",
                    "object_type",
                    "mode",
                    "uid",
                    "gid",
                )
            }
            if name in APPLICATION_DIRECTORY_MOUNT_SOURCES
            else object_identity
        )
        normalized[name] = {
            "source_path_digest": _digest(
                record.get("source_path_digest"),
                f"application mount source identity {name}.source_path_digest",
            ),
            "object_identity": digest_identity,
            "parent_identity": {
                field: parent_identity[field]
                for field in (
                    "device",
                    "inode",
                    "object_type",
                    "mode",
                    "uid",
                    "gid",
                )
            },
            "ancestor_identities": [
                {
                    field: ancestor[field]
                    for field in (
                        "device",
                        "inode",
                        "object_type",
                        "mode",
                        "uid",
                        "gid",
                    )
                }
                for ancestor in ancestor_identities
            ],
        }
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-application-mount-source-objects-v4",
            "source_identities": normalized,
        }
    )


def application_mount_sources_digest(
    sources: Mapping[str, str],
    *,
    _identity_provider: Callable[[str, str], Mapping[str, Any]] | None = None,
    expected_uid: int = 10001,
    expected_gid: int = 10001,
) -> str:
    """Digest exact host path and stable object identities without returning paths.

    The production path uses no-follow descriptor snapshots.  The private
    provider seam exists only so platform-independent unit tests can exercise
    receipt logic without manufacturing Linux container mount namespaces.
    """

    if set(sources) != APPLICATION_MOUNT_SOURCE_NAMES:
        raise SpringLaunchEvidenceError(
            "application mount sources must contain the exact controlled set"
        )
    identities: dict[str, dict[str, Any]] = {}
    normalized_paths: set[str] = set()
    for name in sorted(APPLICATION_MOUNT_SOURCE_NAMES):
        source = sources[name]
        if (
            not isinstance(source, str)
            or not source
            or source != source.strip()
            or "\x00" in source
            or not Path(source).is_absolute()
            or Path(source) == Path("/")
            or Path(source) != Path(os.path.normpath(source))
        ):
            raise SpringLaunchEvidenceError(
                f"application mount source {name} must be a normalized absolute non-root path"
            )
        if source in normalized_paths:
            # engine HMAC is represented once even though both services consume it;
            # every other semantic source must be isolated.
            raise SpringLaunchEvidenceError(
                "application mount sources must be distinct by semantic role"
            )
        normalized_paths.add(source)
        snapshot = (
            _identity_provider(name, source)
            if _identity_provider is not None
            else _snapshot_mount_source_identity(
                source, f"application mount source {name}"
            )
        )
        snapshot_value = _object(snapshot, f"application mount source {name}.snapshot")
        _exact_fields(
            snapshot_value,
            {"object_identity", "parent_identity", "ancestor_identities"},
            f"application mount source {name}.snapshot",
        )
        validated_identity = _validated_mount_object_identity(
            snapshot_value.get("object_identity"),
            f"application mount source {name}.object_identity",
        )
        validated_parent = _validated_mount_object_identity(
            snapshot_value.get("parent_identity"),
            f"application mount source {name}.parent_identity",
        )
        raw_ancestors = snapshot_value.get("ancestor_identities")
        if not isinstance(raw_ancestors, list) or not raw_ancestors:
            raise SpringLaunchEvidenceError(
                f"application mount source {name}.ancestor_identities must be non-empty"
            )
        ancestor_identities = [
            _validated_mount_object_identity(
                item,
                f"application mount source {name}.ancestor_identities[{index}]",
            )
            for index, item in enumerate(raw_ancestors)
        ]
        _validate_application_mount_object_contract(
            name,
            validated_identity,
            validated_parent,
            ancestor_identities,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            label=f"application mount source {name}",
        )
        identities[name] = {
            "source_path_digest": _mount_source_path_digest(source),
            "object_identity": validated_identity,
            "parent_identity": validated_parent,
            "ancestor_identities": ancestor_identities,
        }
    return _application_mount_source_identities_digest(identities)


def _snapshot_local_json_evidence_reference(
    value: Any,
    *,
    roots: tuple[Path, ...],
    label: str,
) -> ContentObservation:
    reference = _object(value, label)
    _exact_fields(reference, EVIDENCE_REFERENCE_FIELDS, label)
    digest = _digest(reference.get("digest"), f"{label}.digest")
    size = _positive_size(reference.get("size_bytes"), f"{label}.size_bytes")
    if reference.get("media_type") != "application/json":
        raise SpringLaunchEvidenceError(f"{label}.media_type must be application/json")
    uri = _immutable_uri(reference.get("uri"), digest, f"{label}.uri")
    if urlparse(uri).scheme != "file":
        raise SpringLaunchEvidenceError(f"{label}.uri must be a local file URI")
    verification = _object(reference.get("verification"), f"{label}.verification")
    _exact_fields(verification, {"mode", "local_uri"}, f"{label}.verification")
    if verification.get("mode") != "LOCAL_BYTES":
        raise SpringLaunchEvidenceError(
            f"{label}.verification.mode must be exactly LOCAL_BYTES"
        )
    if verification.get("local_uri") != uri:
        raise SpringLaunchEvidenceError(
            f"{label}.verification.local_uri must equal its immutable local URI"
        )
    return _snapshot_content_reference(
        {
            "uri": uri,
            "digest": digest,
            "size_bytes": size,
            "media_type": "application/json",
        },
        roots,
        f"{label}.local_bytes",
        max_bytes=MAX_JSON_BYTES,
        capture_content=True,
    )


def _container_environment_assignments(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, list):
        raise SpringLaunchEvidenceError(f"{label} must be an array")
    values: dict[str, str] = {}
    normalized_names: dict[str, str] = {}
    for index, raw in enumerate(value):
        if not isinstance(raw, str):
            raise SpringLaunchEvidenceError(f"{label}[{index}] must be a string assignment")
        match = DOCKER_ENVIRONMENT_ASSIGNMENT.fullmatch(raw)
        if match is None:
            raise SpringLaunchEvidenceError(
                f"{label}[{index}] must be an exact NAME=VALUE assignment"
            )
        name, item = match.groups()
        if name in values:
            raise SpringLaunchEvidenceError(f"{label} contains duplicate key {name}")
        normalized = _normalized_environment_name(name)
        prior = normalized_names.setdefault(normalized, name)
        if prior != name:
            raise SpringLaunchEvidenceError(
                f"{label} contains relaxed-binding aliases {prior} and {name}"
            )
        values[name] = item
    return values


def _read_small_proc_file(parent_descriptor: int, name: str, label: str) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > 16 * 1024:
            raise SpringLaunchEvidenceError(f"{label} is not a bounded regular proc file")
        chunks: list[bytes] = []
        total = 0
        while total <= 16 * 1024:
            chunk = os.read(descriptor, min(4096, 16 * 1024 + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > 16 * 1024:
            raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
        completed = os.fstat(descriptor)
        if _stat_identity(opened) != _stat_identity(completed):
            raise SpringLaunchEvidenceError(f"{label} changed while it was read")
        return b"".join(chunks)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"{label} could not be read safely: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _proc_process_identity(
    process_descriptor: int, process_id: int, label: str
) -> str:
    raw_stat = _read_small_proc_file(process_descriptor, "stat", f"{label}.stat")
    try:
        rendered = raw_stat.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise SpringLaunchEvidenceError(f"{label}.stat is not ASCII") from exc
    close_parenthesis = rendered.rfind(")")
    fields = rendered[close_parenthesis + 1 :].strip().split()
    if close_parenthesis < 2 or len(fields) < 20 or not fields[19].isdigit():
        raise SpringLaunchEvidenceError(f"{label}.stat has an invalid process identity")
    try:
        namespace = os.stat(
            "ns/mnt", dir_fd=process_descriptor, follow_symlinks=True
        )
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} mount namespace identity could not be read"
        ) from exc
    process_stat = os.fstat(process_descriptor)
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-container-process-identity-v1",
            "pid": process_id,
            "process_directory_device": process_stat.st_dev,
            "process_directory_inode": process_stat.st_ino,
            "start_time_ticks": fields[19],
            "mount_namespace_device": namespace.st_dev,
            "mount_namespace_inode": namespace.st_ino,
        }
    )


def _observe_live_bind_mount(
    source: str,
    process_id: int,
    destination: str,
    label: str,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, Any],
    list[Mapping[str, Any]],
    str,
]:
    """Compare a host bind source with the inode visible in a live container.

    Docker inspect exposes only path strings.  On Linux the trusted host
    collector therefore opens both the host source and the target through the
    container process' mount namespace.  No file content or raw path is emitted.
    """

    if sys.platform != "linux":
        raise SpringLaunchEvidenceError(
            "live mount-object collection requires a Linux Docker host"
        )
    if type(process_id) is not int or process_id <= 1:
        raise SpringLaunchEvidenceError(f"{label} process ID is invalid")
    if (
        not isinstance(destination, str)
        or not destination.startswith("/")
        or Path(destination) == Path("/")
        or Path(destination) != Path(os.path.normpath(destination))
    ):
        raise SpringLaunchEvidenceError(f"{label} destination is invalid")

    source_opened = _open_absolute_mount_source(Path(source), f"{label}.source")
    proc_descriptor = -1
    process_descriptor = -1
    root_descriptor = -1
    target_parent_descriptor = -1
    target_descriptor = -1
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    root_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    object_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        source_before = os.fstat(source_opened.descriptor)
        source_ancestor_before = [
            os.fstat(descriptor)
            for descriptor in source_opened.ancestor_descriptors
        ]
        proc_descriptor = os.open("/proc", directory_flags)
        process_descriptor = os.open(
            str(process_id), directory_flags, dir_fd=proc_descriptor
        )
        process_before = _proc_process_identity(
            process_descriptor, process_id, f"{label}.process"
        )
        # /proc/<pid>/root is an intentional kernel magic link into the
        # already authenticated process mount namespace.  Every component
        # below that root is still opened with O_NOFOLLOW.
        root_descriptor = os.open("root", root_flags, dir_fd=process_descriptor)
        target_parent_descriptor = root_descriptor
        root_descriptor = -1
        parts = Path(destination).parts[1:]
        for part in parts[:-1]:
            next_descriptor = os.open(
                part, directory_flags, dir_fd=target_parent_descriptor
            )
            os.close(target_parent_descriptor)
            target_parent_descriptor = next_descriptor
        target_descriptor = os.open(
            parts[-1], object_flags, dir_fd=target_parent_descriptor
        )
        target_before = os.fstat(target_descriptor)
        if not (
            stat.S_ISREG(target_before.st_mode) or stat.S_ISDIR(target_before.st_mode)
        ):
            raise SpringLaunchEvidenceError(
                f"{label} container target must be a regular file or directory"
            )
        source_path_after = os.stat(
            source_opened.filename,
            dir_fd=source_opened.parent_descriptor,
            follow_symlinks=False,
        )
        source_after = os.fstat(source_opened.descriptor)
        source_ancestor_after = [
            os.fstat(descriptor)
            for descriptor in source_opened.ancestor_descriptors
        ]
        source_ancestor_path_after = [
            os.stat(source_opened.path.anchor, follow_symlinks=False)
        ]
        for index, part in enumerate(source_opened.path.parts[1:-1], start=1):
            source_ancestor_path_after.append(
                os.stat(
                    part,
                    dir_fd=source_opened.ancestor_descriptors[index - 1],
                    follow_symlinks=False,
                )
            )
        target_after = os.fstat(target_descriptor)
        process_after = _proc_process_identity(
            process_descriptor, process_id, f"{label}.process"
        )
        if (
            _stat_identity(source_before) != _stat_identity(source_path_after)
            or _stat_identity(source_before) != _stat_identity(source_after)
            or any(
                _stat_identity(left) != _stat_identity(right)
                for left, right in zip(
                    source_ancestor_before, source_ancestor_after, strict=True
                )
            )
            or any(
                _stat_identity(left) != _stat_identity(right)
                for left, right in zip(
                    source_ancestor_before,
                    source_ancestor_path_after,
                    strict=True,
                )
            )
        ):
            raise SpringLaunchEvidenceError(
                f"{label} host source changed during live mount collection"
            )
        if _stat_identity(target_before) != _stat_identity(target_after):
            raise SpringLaunchEvidenceError(
                f"{label} container target changed during live mount collection"
            )
        if _stat_identity(source_before) != _stat_identity(target_before):
            raise SpringLaunchEvidenceError(
                f"{label} container target does not expose the current host source object"
            )
        if process_before != process_after:
            raise SpringLaunchEvidenceError(
                f"{label} container process restarted during live mount collection"
            )
        return (
            _mount_object_identity(source_before),
            _mount_object_identity(target_before),
            _mount_object_identity(source_ancestor_before[-1]),
            [
                _mount_object_identity(value)
                for value in source_ancestor_before
            ],
            process_before,
        )
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"{label} live mount identity could not be captured safely: {exc}"
        ) from exc
    finally:
        for descriptor in (
            target_descriptor,
            target_parent_descriptor,
            root_descriptor,
            process_descriptor,
            proc_descriptor,
            source_opened.descriptor,
        ):
            if descriptor >= 0:
                os.close(descriptor)
        for descriptor in reversed(source_opened.ancestor_descriptors):
            os.close(descriptor)


LiveMountObserver = Callable[
    [str, int, str, str],
    tuple[
        Mapping[str, Any],
        Mapping[str, Any],
        Mapping[str, Any],
        list[Mapping[str, Any]],
        str,
    ],
]


def _runtime_for_service(
    service: str,
    worker: ContainerRuntimeObservation,
    web: ContainerRuntimeObservation,
) -> ContainerRuntimeObservation:
    if service == "java-engine-worker":
        return worker
    if service == "web-console":
        return web
    raise SpringLaunchEvidenceError(f"unsupported application mount service {service}")


def _collect_application_mount_observations(
    worker: ContainerRuntimeObservation,
    web: ContainerRuntimeObservation,
    *,
    observer: LiveMountObserver,
) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for semantic_name in sorted(APPLICATION_MOUNT_SOURCE_NAMES):
        expected_bindings = APPLICATION_MOUNT_BINDINGS[semantic_name]
        source: str | None = None
        object_identity: dict[str, Any] | None = None
        parent_identity: dict[str, Any] | None = None
        ancestor_identities: list[dict[str, Any]] | None = None
        bindings: list[dict[str, Any]] = []
        for service, destination in expected_bindings:
            runtime = _runtime_for_service(service, worker, web)
            observed_source = runtime.mount_sources[destination]
            if source is None:
                source = observed_source
            elif observed_source != source:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} must use one identical host source across services"
                )
            (
                raw_host,
                raw_target,
                raw_parent,
                raw_ancestors,
                process_identity,
            ) = observer(
                observed_source,
                runtime.process_id,
                destination,
                f"application mount {semantic_name} ({service})",
            )
            host_identity = _validated_mount_object_identity(
                raw_host, f"application mount {semantic_name} host object"
            )
            target_identity = _validated_mount_object_identity(
                raw_target, f"application mount {semantic_name} container object"
            )
            validated_parent = _validated_mount_object_identity(
                raw_parent, f"application mount {semantic_name} source parent"
            )
            if not isinstance(raw_ancestors, list) or not raw_ancestors:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} source ancestry must be non-empty"
                )
            validated_ancestors = [
                _validated_mount_object_identity(
                    item,
                    f"application mount {semantic_name} source ancestry[{index}]",
                )
                for index, item in enumerate(raw_ancestors)
            ]
            if host_identity != target_identity:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} container target does not match the host source object"
                )
            expected_type = (
                "DIRECTORY"
                if semantic_name in APPLICATION_DIRECTORY_MOUNT_SOURCES
                else "REGULAR_FILE"
            )
            if host_identity["object_type"] != expected_type:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} must bind a {expected_type.lower()}"
                )
            _validate_application_mount_object_contract(
                semantic_name,
                host_identity,
                validated_parent,
                validated_ancestors,
                expected_uid=10001,
                expected_gid=10001,
                label=f"application mount {semantic_name}",
            )
            if object_identity is None:
                object_identity = host_identity
            elif object_identity != host_identity:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} changed between container observations"
                )
            if parent_identity is None:
                parent_identity = validated_parent
                ancestor_identities = validated_ancestors
            elif (
                parent_identity != validated_parent
                or ancestor_identities != validated_ancestors
            ):
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} ancestry changed between container observations"
                )
            bindings.append(
                {
                    "service": service,
                    "container_id": runtime.container_id,
                    "process_id": runtime.process_id,
                    "process_identity_digest": _digest(
                        process_identity,
                        f"application mount {semantic_name} process identity",
                    ),
                    "destination": destination,
                }
            )
        assert (
            source is not None
            and object_identity is not None
            and parent_identity is not None
            and ancestor_identities is not None
        )
        observations[semantic_name] = {
            "source_path_digest": _mount_source_path_digest(source),
            "object_identity": object_identity,
            "parent_identity": parent_identity,
            "ancestor_identities": ancestor_identities,
            "bindings": bindings,
        }
    return observations


def _validate_application_mount_observations(
    value: Any,
    *,
    worker: ContainerRuntimeObservation,
    web_container_id: str,
    web_process_id: int,
    web_mount_source_digests: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]], str]:
    raw_observations = _object(value, "web-console runtime attestation.mount_sources")
    if set(raw_observations) != APPLICATION_MOUNT_SOURCE_NAMES:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation mount sources must contain the exact controlled set"
        )
    normalized: dict[str, dict[str, Any]] = {}
    for semantic_name in sorted(APPLICATION_MOUNT_SOURCE_NAMES):
        raw = _object(
            raw_observations.get(semantic_name),
            f"web-console runtime attestation.mount_sources.{semantic_name}",
        )
        _exact_fields(
            raw,
            {
                "source_path_digest",
                "object_identity",
                "parent_identity",
                "ancestor_identities",
                "bindings",
            },
            f"web-console runtime attestation.mount_sources.{semantic_name}",
        )
        expected_bindings = APPLICATION_MOUNT_BINDINGS[semantic_name]
        source_path_digest: str | None = None
        expected_binding_values: list[dict[str, Any]] = []
        for service, destination in expected_bindings:
            if service == "java-engine-worker":
                container_id = worker.container_id
                process_id = worker.process_id
                observed_source_digest = _mount_source_path_digest(
                    worker.mount_sources[destination]
                )
            elif service == "web-console":
                container_id = web_container_id
                process_id = web_process_id
                observed_source_digest = web_mount_source_digests[destination]
            else:
                raise SpringLaunchEvidenceError(
                    f"unsupported application mount service {service}"
                )
            if source_path_digest is None:
                source_path_digest = observed_source_digest
            elif source_path_digest != observed_source_digest:
                raise SpringLaunchEvidenceError(
                    f"application mount {semantic_name} has inconsistent inspected host sources"
                )
            expected_binding_values.append(
                {
                    "service": service,
                    "container_id": container_id,
                    "process_id": process_id,
                    "destination": destination,
                }
            )
        assert source_path_digest is not None
        if raw.get("source_path_digest") != source_path_digest:
            raise SpringLaunchEvidenceError(
                f"application mount {semantic_name} source path digest does not match docker inspect"
            )
        object_identity = _validated_mount_object_identity(
            raw.get("object_identity"),
            f"web-console runtime attestation.mount_sources.{semantic_name}.object_identity",
        )
        parent_identity = _validated_mount_object_identity(
            raw.get("parent_identity"),
            f"web-console runtime attestation.mount_sources.{semantic_name}.parent_identity",
        )
        raw_ancestors = raw.get("ancestor_identities")
        if not isinstance(raw_ancestors, list) or not raw_ancestors:
            raise SpringLaunchEvidenceError(
                f"application mount {semantic_name} ancestry must be non-empty"
            )
        ancestor_identities = [
            _validated_mount_object_identity(
                item,
                f"web-console runtime attestation.mount_sources.{semantic_name}.ancestor_identities[{index}]",
            )
            for index, item in enumerate(raw_ancestors)
        ]
        expected_type = (
            "DIRECTORY"
            if semantic_name in APPLICATION_DIRECTORY_MOUNT_SOURCES
            else "REGULAR_FILE"
        )
        if object_identity["object_type"] != expected_type:
            raise SpringLaunchEvidenceError(
                f"application mount {semantic_name} has the wrong object type"
            )
        _validate_application_mount_object_contract(
            semantic_name,
            object_identity,
            parent_identity,
            ancestor_identities,
            expected_uid=10001,
            expected_gid=10001,
            label=f"application mount {semantic_name}",
        )
        raw_bindings = raw.get("bindings")
        if not isinstance(raw_bindings, list) or len(raw_bindings) != len(
            expected_binding_values
        ):
            raise SpringLaunchEvidenceError(
                f"application mount {semantic_name} bindings are incomplete"
            )
        normalized_bindings: list[dict[str, Any]] = []
        for index, (raw_binding, expected) in enumerate(
            zip(raw_bindings, expected_binding_values, strict=True)
        ):
            binding = _object(
                raw_binding,
                f"web-console runtime attestation.mount_sources.{semantic_name}.bindings[{index}]",
            )
            _exact_fields(
                binding,
                {
                    "service",
                    "container_id",
                    "process_id",
                    "process_identity_digest",
                    "destination",
                },
                f"web-console runtime attestation.mount_sources.{semantic_name}.bindings[{index}]",
            )
            for field, expected_value in expected.items():
                actual = binding.get(field)
                if type(actual) is not type(expected_value) or actual != expected_value:
                    raise SpringLaunchEvidenceError(
                        f"application mount {semantic_name} binding {field} does not match the inspected container"
                    )
            normalized_bindings.append(
                {
                    **expected,
                    "process_identity_digest": _digest(
                        binding.get("process_identity_digest"),
                        f"application mount {semantic_name} process identity",
                    ),
                }
            )
        normalized[semantic_name] = {
            "source_path_digest": _digest(
                raw.get("source_path_digest"),
                f"application mount {semantic_name} source path digest",
            ),
            "object_identity": object_identity,
            "parent_identity": parent_identity,
            "ancestor_identities": ancestor_identities,
            "bindings": normalized_bindings,
        }
    aggregate = _application_mount_source_identities_digest(
        {
            name: {
                "source_path_digest": item["source_path_digest"],
                "object_identity": item["object_identity"],
                "parent_identity": item["parent_identity"],
                "ancestor_identities": item["ancestor_identities"],
            }
            for name, item in normalized.items()
        }
    )
    return normalized, aggregate


def _validated_mount_sources(
    value: Any,
    *,
    label: str,
    expected_destinations: Mapping[str, bool],
) -> dict[str, str]:
    if not isinstance(value, list):
        raise SpringLaunchEvidenceError(f"{label} must be an array")
    sources: dict[str, str] = {}
    for index, item in enumerate(value):
        mount = _object(item, f"{label}[{index}]")
        _exact_fields(
            mount,
            {"Type", "Source", "Destination", "Mode", "RW", "Propagation"},
            f"{label}[{index}]",
        )
        destination = mount.get("Destination")
        if not isinstance(destination, str) or destination not in expected_destinations:
            raise SpringLaunchEvidenceError(
                f"{label} contains an undeclared mount destination {destination!r}"
            )
        if destination in sources:
            raise SpringLaunchEvidenceError(
                f"{label} contains duplicate mount destination {destination}"
            )
        expected_rw = expected_destinations[destination]
        expected_mode = "rw" if expected_rw else "ro"
        if (
            mount.get("Type") != "bind"
            or mount.get("RW") is not expected_rw
            or mount.get("Mode") != expected_mode
            or mount.get("Propagation") != "rprivate"
        ):
            raise SpringLaunchEvidenceError(
                f"{label} mount {destination} must be an exact {expected_mode} rprivate bind"
            )
        source = mount.get("Source")
        if (
            not isinstance(source, str)
            or not source
            or source != source.strip()
            or "\x00" in source
            or not Path(source).is_absolute()
            or Path(source) == Path("/")
            or Path(source) != Path(os.path.normpath(source))
        ):
            raise SpringLaunchEvidenceError(
                f"{label} mount {destination} must use a normalized absolute non-root host source"
            )
        sources[destination] = source
    if set(sources) != set(expected_destinations):
        missing = sorted(set(expected_destinations) - set(sources))
        raise SpringLaunchEvidenceError(
            f"{label} is missing required mount destinations: {', '.join(missing)}"
        )
    if len(set(sources.values())) != len(sources):
        raise SpringLaunchEvidenceError(f"{label} host mount sources must be distinct")
    return sources


def _validate_tmpfs(
    value: Any,
    *,
    label: str,
    expected_sizes: Mapping[str, frozenset[str]],
) -> None:
    tmpfs = _object(value, label)
    if set(tmpfs) != set(expected_sizes):
        raise SpringLaunchEvidenceError(
            f"{label} mount points do not match the controlled Compose contract"
        )
    for destination, rendered in tmpfs.items():
        if not isinstance(rendered, str):
            raise SpringLaunchEvidenceError(f"{label}.{destination} options must be a string")
        options = rendered.split(",")
        size_options = {item for item in options if item.startswith("size=")}
        if (
            set(options) - size_options != {"rw", "noexec", "nosuid"}
            or len(size_options) != 1
            or next(iter(size_options)).removeprefix("size=") not in expected_sizes[destination]
        ):
            raise SpringLaunchEvidenceError(
                f"{label}.{destination} must be rw,noexec,nosuid with the exact bounded size"
            )


def _validate_container_runtime_security(
    container: dict[str, Any],
    config: dict[str, Any],
    *,
    label: str,
    service: str,
    expected_image_digest: str,
    expected_entrypoint: tuple[str, ...],
    expected_command: tuple[str, ...] | None,
    expected_working_directory: str,
    expected_mounts: Mapping[str, bool],
    expected_network_suffixes: frozenset[str],
    expected_tmpfs_sizes: Mapping[str, frozenset[str]],
    expected_pids_limit: int,
    expected_exposed_port: str,
) -> ContainerRuntimeObservation:
    labels = _object(config.get("Labels"), f"{label}.Config.Labels")
    if labels.get("com.docker.compose.service") != service:
        raise SpringLaunchEvidenceError(
            f"{label} must identify the unique {service} Compose service"
        )
    project = _identity(
        labels.get("com.docker.compose.project"), f"{label} Compose project identity"
    )
    container_id = container.get("Id")
    if not isinstance(container_id, str) or re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise SpringLaunchEvidenceError(f"{label}.Id must be an exact Docker container ID")
    container_name = container.get("Name")
    if (
        not isinstance(container_name, str)
        or not container_name.startswith("/")
        or service not in container_name
        or project not in container_name
    ):
        raise SpringLaunchEvidenceError(
            f"{label}.Name does not bind the Compose project and service"
        )
    state = _object(container.get("State"), f"{label}.State")
    if (
        state.get("Running") is not True
        or state.get("Restarting") is not False
        or state.get("Dead") is not False
    ):
        raise SpringLaunchEvidenceError(f"{label}.State must be stably running")
    process_id = state.get("Pid")
    if type(process_id) is not int or process_id <= 1:
        raise SpringLaunchEvidenceError(
            f"{label}.State.Pid must be a positive live host process ID"
        )
    image_digest = _digest(container.get("Image"), f"{label}.Image")
    if image_digest != expected_image_digest:
        raise SpringLaunchEvidenceError(
            f"{label} immutable {service} image digest does not match the signed environment manifest"
        )
    configured_image = config.get("Image")
    if (
        not isinstance(configured_image, str)
        or not configured_image
        or len(configured_image) > 512
        or any(character.isspace() or ord(character) < 0x20 for character in configured_image)
        or configured_image.casefold() == "latest"
        or configured_image.casefold().endswith(":latest")
    ):
        raise SpringLaunchEvidenceError(
            f"{label}.Config.Image must be a bounded non-latest image reference"
        )
    entrypoint = config.get("Entrypoint")
    if not isinstance(entrypoint, list) or tuple(entrypoint) != expected_entrypoint:
        raise SpringLaunchEvidenceError(
            f"{label}.Config.Entrypoint must exactly match the controlled {service} image entrypoint"
        )
    command = config.get("Cmd")
    if expected_command is None:
        if command is not None and command != []:
            raise SpringLaunchEvidenceError(
                f"{label}.Config.Cmd must be null or an empty array"
            )
    elif not isinstance(command, list) or tuple(command) != expected_command:
        raise SpringLaunchEvidenceError(
            f"{label}.Config.Cmd must exactly match the controlled {service} command"
        )
    expected_process_args = expected_entrypoint[1:] + (
        () if expected_command is None else expected_command
    )
    if (
        container.get("Path") != expected_entrypoint[0]
        or container.get("Args") != list(expected_process_args)
    ):
        raise SpringLaunchEvidenceError(
            f"{label} running Path/Args do not match the controlled {service} process"
        )
    if config.get("User") != "10001:10001":
        raise SpringLaunchEvidenceError(f"{label}.Config.User must equal 10001:10001")
    if config.get("WorkingDir") != expected_working_directory:
        raise SpringLaunchEvidenceError(
            f"{label}.Config.WorkingDir must equal {expected_working_directory}"
        )
    exposed_ports = _object(config.get("ExposedPorts"), f"{label}.Config.ExposedPorts")
    if set(exposed_ports) != {expected_exposed_port}:
        raise SpringLaunchEvidenceError(
            f"{label}.Config.ExposedPorts must contain only {expected_exposed_port}"
        )

    host = _object(container.get("HostConfig"), f"{label}.HostConfig")
    exact = {
        "ReadonlyRootfs": True,
        "Privileged": False,
        "PidMode": "",
        "IpcMode": "private",
        "UTSMode": "",
        "UsernsMode": "",
        "CgroupnsMode": "private",
        "AutoRemove": False,
        "PublishAllPorts": False,
        "Init": True,
        "PidsLimit": expected_pids_limit,
        "Runtime": "runc",
        "Isolation": "",
        "OomKillDisable": False,
    }
    for name, expected in exact.items():
        actual = host.get(name)
        if type(actual) is not type(expected) or actual != expected:
            raise SpringLaunchEvidenceError(
                f"{label}.HostConfig.{name} must equal {expected!r}"
            )
    if host.get("CapAdd") not in (None, []):
        raise SpringLaunchEvidenceError(f"{label}.HostConfig.CapAdd must be empty")
    if host.get("CapDrop") != ["ALL"]:
        raise SpringLaunchEvidenceError(f"{label}.HostConfig.CapDrop must equal ALL")
    if host.get("SecurityOpt") != ["no-new-privileges:true"]:
        raise SpringLaunchEvidenceError(
            f"{label}.HostConfig.SecurityOpt must enable only no-new-privileges"
        )
    if host.get("PortBindings") not in (None, {}):
        raise SpringLaunchEvidenceError(f"{label}.HostConfig.PortBindings must be empty")
    for name in (
        "Devices",
        "DeviceRequests",
        "VolumesFrom",
        "Links",
        "ExtraHosts",
        "Dns",
        "DnsOptions",
        "DnsSearch",
        "GroupAdd",
    ):
        if host.get(name) not in (None, []):
            raise SpringLaunchEvidenceError(f"{label}.HostConfig.{name} must be empty")
    restart = _object(host.get("RestartPolicy"), f"{label}.HostConfig.RestartPolicy")
    if restart.get("Name") != "unless-stopped":
        raise SpringLaunchEvidenceError(
            f"{label}.HostConfig.RestartPolicy.Name must equal unless-stopped"
        )
    _validate_tmpfs(
        host.get("Tmpfs"),
        label=f"{label}.HostConfig.Tmpfs",
        expected_sizes=expected_tmpfs_sizes,
    )
    network_settings = _object(container.get("NetworkSettings"), f"{label}.NetworkSettings")
    networks = _object(network_settings.get("Networks"), f"{label}.NetworkSettings.Networks")
    expected_networks = {f"{project}{suffix}" for suffix in expected_network_suffixes}
    if set(networks) != expected_networks:
        raise SpringLaunchEvidenceError(
            f"{label} networks must exactly match the controlled Compose topology"
        )
    if host.get("NetworkMode") not in expected_networks:
        raise SpringLaunchEvidenceError(
            f"{label}.HostConfig.NetworkMode must select one controlled service network"
        )
    ports = _object(network_settings.get("Ports"), f"{label}.NetworkSettings.Ports")
    if ports != {expected_exposed_port: None}:
        raise SpringLaunchEvidenceError(
            f"{label}.NetworkSettings.Ports must expose only {expected_exposed_port} without host publication"
        )
    sources = _validated_mount_sources(
        container.get("Mounts"),
        label=f"{label}.Mounts",
        expected_destinations=expected_mounts,
    )
    expected_binds = {
        f"{source}:{destination}:{'rw' if expected_mounts[destination] else 'ro'}"
        for destination, source in sources.items()
    }
    binds = host.get("Binds")
    if not isinstance(binds, list) or set(binds) != expected_binds or len(binds) != len(expected_binds):
        raise SpringLaunchEvidenceError(
            f"{label}.HostConfig.Binds must exactly match the inspected rprivate mounts"
        )
    environment = _container_environment_assignments(
        config.get("Env"), f"{label}.Config.Env"
    )
    sanitized_runtime_shape = {
        "container_id": container_id,
        "container_name": container_name,
        "compose_project": project,
        "service": service,
        "process_id": process_id,
        "image_digest": image_digest,
        "image_reference": configured_image,
        "path": expected_entrypoint[0],
        "args": list(expected_process_args),
        "entrypoint": list(expected_entrypoint),
        "command": [] if expected_command is None else list(expected_command),
        "working_directory": expected_working_directory,
        "user": "10001:10001",
        "running": True,
        "restarting": False,
        "dead": False,
        "readonly_rootfs": True,
        "privileged": False,
        "init": True,
        "pids_limit": expected_pids_limit,
        "oci_runtime": "runc",
        "isolation": "",
        "oom_kill_disable": False,
        "publish_all_ports": False,
        "published_ports": [],
        "exposed_port": expected_exposed_port,
        "restart_policy": "unless-stopped",
        "namespace_modes": {
            "pid": "",
            "ipc": "private",
            "uts": "",
            "user": "",
            "cgroup": "private",
        },
        "tmpfs": {
            destination: (
                "rw,noexec,nosuid,size="
                + min(expected_tmpfs_sizes[destination], key=len)
            )
            for destination in sorted(expected_tmpfs_sizes)
        },
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "network_names": sorted(networks),
        "network_mode": host["NetworkMode"],
        "mounts": [
            {
                "destination": destination,
                "read_write": expected_mounts[destination],
                "mode": "rw" if expected_mounts[destination] else "ro",
                "propagation": "rprivate",
                "source_path_digest": _mount_source_path_digest(source),
            }
            for destination, source in sorted(sources.items())
        ],
    }
    return ContainerRuntimeObservation(
        environment=environment,
        image_digest=image_digest,
        configured_image=configured_image,
        engine_secret_source=sources["/run/secrets/elmos-spring-engine-hmac"],
        backend_network=f"{project}_backend",
        mount_sources=sources,
        container_id=container_id,
        container_name=container_name,
        compose_project=project,
        process_id=process_id,
        sanitized_runtime_shape=sanitized_runtime_shape,
    )


def _spring_worker_environment_from_inspect(
    content: bytes,
    *,
    label: str,
    expected_image_digest: str,
) -> ContainerRuntimeObservation:
    document = _load_strict_json_bytes(content, label)
    if not isinstance(document, list) or len(document) != 1:
        raise SpringLaunchEvidenceError(
            f"{label} must contain exactly one java-engine-worker container"
        )
    container = _object(document[0], f"{label}[0]")
    config = _object(container.get("Config"), f"{label}[0].Config")
    runtime = _validate_container_runtime_security(
        container,
        config,
        label=f"{label}[0]",
        service="java-engine-worker",
        expected_image_digest=expected_image_digest,
        expected_entrypoint=SPRING_WORKER_CONTAINER_ENTRYPOINT,
        expected_command=None,
        expected_working_directory="/app",
        expected_mounts={
            "/workspace/private-runner": True,
            "/run/secrets/elmos-verifier-hmac": False,
            "/run/secrets/elmos-transformer-hmac": False,
            "/run/secrets/elmos-runtime-hmac": False,
            "/run/secrets/elmos-spring-engine-hmac": False,
            "/var/lib/elmos/spring-engine-auth-replay": True,
        },
        expected_network_suffixes=frozenset({"_backend"}),
        expected_tmpfs_sizes={
            "/tmp": frozenset({"512m", "536870912"}),
            "/home/elmos/.m2": frozenset({"512m", "536870912"}),
        },
        expected_pids_limit=1024,
        expected_exposed_port="8081/tcp",
    )
    values = runtime.environment
    for name, value in values.items():
        normalized = _normalized_environment_name(name)
        canonical_name = _SPRING_WORKER_ENV_CANONICAL_BY_NORMALIZED.get(normalized)
        if canonical_name is not None and name != canonical_name:
            raise SpringLaunchEvidenceError(
                f"{label} Spring worker override {name} must use exact key {canonical_name}"
            )
        if name in SPRING_WORKER_ALLOWED_EXPLICIT_EMPTY_ENVIRONMENT:
            if value != "":
                raise SpringLaunchEvidenceError(
                    f"{label} dangerous override {name} must be exactly empty"
                )
            values[name] = value
            continue
        if name in SPRING_WORKER_EXECUTION_ENVIRONMENT:
            expected_execution_value = SPRING_WORKER_EXECUTION_ENVIRONMENT[name]
            if value != expected_execution_value:
                raise SpringLaunchEvidenceError(
                    f"{label} execution environment {name} does not match the controlled worker image"
                )
            values[name] = value
            continue
        if _dangerous_spring_worker_environment_name(name):
            raise SpringLaunchEvidenceError(
                f"{label} dangerous override {name} must be absent"
            )
        values[name] = value
        if normalized.startswith("ELMOSSPRING"):
            if canonical_name is None:
                raise SpringLaunchEvidenceError(
                    f"{label} contains unsupported Spring worker override {name}"
                )
        if name not in SPRING_WORKER_EFFECTIVE_ENV_KEYS:
            raise SpringLaunchEvidenceError(
                f"{label} contains undeclared worker environment {name}"
            )
    return runtime


def _validate_web_console_environment(
    environment: Mapping[str, str], *, label: str
) -> tuple[dict[str, str], list[str], str]:
    canonical_required = {
        _normalized_environment_name(name): name
        for name in (
            *WEB_CONSOLE_CONFIGURATION_ENVIRONMENT,
            *WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED,
        )
    }
    for name, value in environment.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise SpringLaunchEvidenceError(
                f"{label} names and values must be strings"
            )
        normalized = _normalized_environment_name(name)
        canonical = canonical_required.get(normalized)
        if canonical is not None:
            if name != canonical:
                raise SpringLaunchEvidenceError(
                    f"{label} override {name} must use exact key {canonical}"
                )
            continue
        if (
            normalized in WEB_CONSOLE_FORBIDDEN_ENVIRONMENT_NORMALIZED
            or normalized.startswith("SPRING")
            or normalized.startswith("SERVER")
            or normalized.startswith("MANAGEMENT")
            or normalized.startswith("ELMOSSPRING")
            or normalized.startswith("LD")
            or normalized.startswith("DYLD")
            or normalized.startswith("NODE")
            or normalized.startswith("YARN")
            or normalized.startswith("JAVA")
            or normalized.startswith("JDK")
            or normalized.startswith("MAVEN")
            or normalized.startswith("GRADLE")
            or normalized.startswith("GIT")
            or normalized.startswith("SSL")
            or normalized.startswith("TLS")
        ):
            raise SpringLaunchEvidenceError(
                f"{label} dangerous process or routing override {name} must be absent"
            )
    required: dict[str, str] = {}
    for name, expected in WEB_CONSOLE_CONFIGURATION_ENVIRONMENT.items():
        actual = environment.get(name)
        if actual != expected:
            raise SpringLaunchEvidenceError(
                f"{label} required non-secret value {name} must equal {expected!r}"
            )
        required[name] = actual
    for name, allowed in WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED.items():
        actual = environment.get(name)
        if actual not in allowed:
            raise SpringLaunchEvidenceError(
                f"{label} required non-secret value {name} is invalid"
            )
        required[name] = actual
    names = sorted(environment)
    return required, names, web_console_environment_names_digest(names)


def _utc_instant_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise SpringLaunchEvidenceError("collector clock must be timezone-aware UTC")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _web_console_runtime_from_inspect(
    raw_inspect: bytes, *, expected_image_digest: str, label: str
) -> ContainerRuntimeObservation:
    if not isinstance(raw_inspect, bytes) or not raw_inspect:
        raise SpringLaunchEvidenceError(f"{label} bytes are required")
    if len(raw_inspect) > MAX_JSON_BYTES:
        raise SpringLaunchEvidenceError(f"{label} exceeds the byte budget")
    document = _load_strict_json_bytes(raw_inspect, label)
    if not isinstance(document, list) or len(document) != 1:
        raise SpringLaunchEvidenceError(f"{label} must contain exactly one container")
    container = _object(document[0], f"{label}[0]")
    config = _object(container.get("Config"), f"{label}[0].Config")
    runtime = _validate_container_runtime_security(
        container,
        config,
        label=f"{label}[0]",
        service="web-console",
        expected_image_digest=expected_image_digest,
        expected_entrypoint=WEB_CONSOLE_CONTAINER_ENTRYPOINT,
        expected_command=WEB_CONSOLE_CONTAINER_COMMAND,
        expected_working_directory="/workspace/apps/web-console",
        expected_mounts={
            "/run/secrets/elmos/resend-api-key": False,
            "/run/secrets/elmos-spring-engine-hmac": False,
        },
        expected_network_suffixes=frozenset({"_edge", "_backend"}),
        expected_tmpfs_sizes={"/tmp": frozenset({"64m", "67108864"})},
        expected_pids_limit=512,
        expected_exposed_port="3000/tcp",
    )
    if runtime.sanitized_runtime_shape["network_mode"] != (
        f"{runtime.compose_project}_edge"
    ):
        raise SpringLaunchEvidenceError(
            f"{label} HostConfig.NetworkMode must select the controlled edge network"
        )
    _validate_web_console_environment(runtime.environment, label=f"{label} Config.Env")
    return runtime


def collect_web_console_runtime_attestation(
    raw_inspect: bytes,
    *,
    raw_worker_inspect: bytes,
    expected_image_digest: str,
    expected_worker_image_digest: str,
    collector_identity: str,
    stable_reinspect: Callable[[], tuple[bytes, bytes]],
    captured_at: datetime | None = None,
    _live_mount_observer: LiveMountObserver = _observe_live_bind_mount,
) -> dict[str, Any]:
    """Validate both live containers and return a secret-free runtime record.

    Docker inspect does not expose bind-mount inodes.  The trusted Linux host
    collector therefore compares every source descriptor with the object seen
    through ``/proc/<pid>/root`` and re-inspects both containers after those
    checks.  The output contains only environment names, required non-secret
    values, path digests and filesystem metadata; it never contains inherited
    secret values or raw host paths.  No signature or external pass is created.
    """

    expected_image = _digest(expected_image_digest, "expected web image digest")
    expected_worker_image = _digest(
        expected_worker_image_digest, "expected worker image digest"
    )
    collector = _identity(collector_identity, "collector identity")
    if not callable(stable_reinspect):
        raise SpringLaunchEvidenceError(
            "a trusted stable Docker reinspection callback is required"
        )
    web_runtime = _web_console_runtime_from_inspect(
        raw_inspect,
        expected_image_digest=expected_image,
        label="live web-console docker inspect",
    )
    if not isinstance(raw_worker_inspect, bytes) or not raw_worker_inspect:
        raise SpringLaunchEvidenceError(
            "live java-engine-worker docker inspect bytes are required"
        )
    if len(raw_worker_inspect) > MAX_JSON_BYTES:
        raise SpringLaunchEvidenceError(
            "live java-engine-worker docker inspect exceeds the byte budget"
        )
    worker_runtime = _spring_worker_environment_from_inspect(
        raw_worker_inspect,
        label="live java-engine-worker docker inspect",
        expected_image_digest=expected_worker_image,
    )
    if web_runtime.compose_project != worker_runtime.compose_project:
        raise SpringLaunchEvidenceError(
            "live web-console and worker must belong to one Compose project"
        )
    if web_runtime.backend_network != worker_runtime.backend_network:
        raise SpringLaunchEvidenceError(
            "live web-console and worker must share the controlled backend network"
        )
    mount_observations = _collect_application_mount_observations(
        worker_runtime,
        web_runtime,
        observer=_live_mount_observer,
    )
    application_mount_digest = _application_mount_source_identities_digest(
        {
            name: {
                "source_path_digest": value["source_path_digest"],
                "object_identity": value["object_identity"],
                "parent_identity": value["parent_identity"],
                "ancestor_identities": value["ancestor_identities"],
            }
            for name, value in mount_observations.items()
        }
    )
    try:
        raw_web_after, raw_worker_after = stable_reinspect()
    except Exception as exc:  # noqa: BLE001 - adapters must fail closed
        raise SpringLaunchEvidenceError(
            "trusted Docker reinspection failed closed"
        ) from exc
    web_after = _web_console_runtime_from_inspect(
        raw_web_after,
        expected_image_digest=expected_image,
        label="stable web-console Docker reinspection",
    )
    worker_after = _spring_worker_environment_from_inspect(
        raw_worker_after,
        label="stable java-engine-worker Docker reinspection",
        expected_image_digest=expected_worker_image,
    )
    if web_runtime != web_after or worker_runtime != worker_after:
        raise SpringLaunchEvidenceError(
            "web-console or worker changed during live runtime collection"
        )
    required, names, names_digest = _validate_web_console_environment(
        web_runtime.environment,
        label="live web-console Config.Env",
    )
    captured = captured_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "method": WEB_RUNTIME_ATTESTATION_METHOD,
        "captured_at": _utc_instant_text(captured),
        "collector_identity": collector,
        "raw_inspect_digest": "sha256:" + hashlib.sha256(raw_inspect).hexdigest(),
        "raw_inspect_size_bytes": len(raw_inspect),
        "raw_worker_inspect_digest": "sha256:"
        + hashlib.sha256(raw_worker_inspect).hexdigest(),
        "raw_worker_inspect_size_bytes": len(raw_worker_inspect),
        "worker_container_id": worker_runtime.container_id,
        "runtime": web_runtime.sanitized_runtime_shape,
        "mount_sources": mount_observations,
        "application_mount_sources_digest": application_mount_digest,
        "stable_reinspection": True,
        "environment_names": names,
        "environment_names_digest": names_digest,
        "required_environment": required,
        "effective_web_console_configuration_digest": (
            web_console_configuration_digest(required)
        ),
        "secrets_embedded": False,
    }


def _validate_sanitized_runtime_shape(
    value: Any, *, expected_image_digest: str
) -> tuple[dict[str, str], str, str, str, int]:
    runtime = _object(value, "web-console runtime attestation.runtime")
    fields = {
        "container_id",
        "container_name",
        "compose_project",
        "service",
        "process_id",
        "image_digest",
        "image_reference",
        "path",
        "args",
        "entrypoint",
        "command",
        "working_directory",
        "user",
        "running",
        "restarting",
        "dead",
        "readonly_rootfs",
        "privileged",
        "init",
        "pids_limit",
        "oci_runtime",
        "isolation",
        "oom_kill_disable",
        "publish_all_ports",
        "published_ports",
        "exposed_port",
        "restart_policy",
        "namespace_modes",
        "tmpfs",
        "cap_drop",
        "security_opt",
        "network_names",
        "network_mode",
        "mounts",
    }
    _exact_fields(runtime, fields, "web-console runtime attestation.runtime")
    container_id = runtime.get("container_id")
    if not isinstance(container_id, str) or re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation container_id is invalid"
        )
    process_id = runtime.get("process_id")
    if type(process_id) is not int or process_id <= 1:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation process_id is invalid"
        )
    project = _identity(
        runtime.get("compose_project"),
        "web-console runtime attestation compose_project",
    )
    container_name = runtime.get("container_name")
    if (
        not isinstance(container_name, str)
        or not container_name.startswith("/")
        or "web-console" not in container_name
        or project not in container_name
        or runtime.get("service") != "web-console"
    ):
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation container identity is invalid"
        )
    if runtime.get("image_digest") != expected_image_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation image digest does not match the signed manifest"
        )
    _digest(runtime.get("image_digest"), "web-console runtime image digest")
    image_reference = runtime.get("image_reference")
    if (
        not isinstance(image_reference, str)
        or not image_reference
        or len(image_reference) > 512
        or any(character.isspace() or ord(character) < 0x20 for character in image_reference)
        or image_reference.casefold() == "latest"
        or image_reference.casefold().endswith(":latest")
    ):
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation image_reference is invalid"
        )
    expected_args = list(WEB_CONSOLE_CONTAINER_COMMAND)
    exact_values = {
        "path": WEB_CONSOLE_CONTAINER_ENTRYPOINT[0],
        "args": expected_args,
        "entrypoint": list(WEB_CONSOLE_CONTAINER_ENTRYPOINT),
        "command": expected_args,
        "working_directory": "/workspace/apps/web-console",
        "user": "10001:10001",
        "running": True,
        "restarting": False,
        "dead": False,
        "readonly_rootfs": True,
        "privileged": False,
        "init": True,
        "pids_limit": 512,
        "oci_runtime": "runc",
        "isolation": "",
        "oom_kill_disable": False,
        "publish_all_ports": False,
        "published_ports": [],
        "exposed_port": "3000/tcp",
        "restart_policy": "unless-stopped",
        "namespace_modes": {
            "pid": "",
            "ipc": "private",
            "uts": "",
            "user": "",
            "cgroup": "private",
        },
        "tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "network_names": sorted({f"{project}_edge", f"{project}_backend"}),
        "network_mode": f"{project}_edge",
    }
    for name, expected in exact_values.items():
        actual = runtime.get(name)
        if type(actual) is not type(expected) or actual != expected:
            raise SpringLaunchEvidenceError(
                f"web-console runtime attestation.runtime.{name} is invalid"
            )
    raw_mounts = runtime.get("mounts")
    if not isinstance(raw_mounts, list):
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation.runtime.mounts must be an array"
        )
    expected_destinations = {
        "/run/secrets/elmos/resend-api-key",
        "/run/secrets/elmos-spring-engine-hmac",
    }
    mounts: dict[str, str] = {}
    for index, raw in enumerate(raw_mounts):
        mount = _object(raw, f"web-console runtime attestation.runtime.mounts[{index}]")
        _exact_fields(
            mount,
            {
                "destination",
                "read_write",
                "mode",
                "propagation",
                "source_path_digest",
            },
            f"web-console runtime attestation.runtime.mounts[{index}]",
        )
        destination = mount.get("destination")
        if destination not in expected_destinations or destination in mounts:
            raise SpringLaunchEvidenceError(
                "web-console runtime attestation contains an undeclared or duplicate mount"
            )
        if (
            mount.get("read_write") is not False
            or mount.get("mode") != "ro"
            or mount.get("propagation") != "rprivate"
        ):
            raise SpringLaunchEvidenceError(
                f"web-console runtime mount {destination} must be an exact ro rprivate bind"
            )
        mounts[destination] = _digest(
            mount.get("source_path_digest"),
            f"web-console runtime mount {destination} source path digest",
        )
    if set(mounts) != expected_destinations or len(set(mounts.values())) != 2:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation must contain two distinct controlled mounts"
        )
    return mounts, project, image_reference, container_id, process_id


def _validate_web_console_runtime_attestation(
    observation: ContentObservation,
    *,
    expected_image_digest: str,
    worker: ContainerRuntimeObservation,
    worker_inspect_digest: str,
    worker_inspect_size_bytes: int,
    observed_at: datetime,
    max_age: timedelta,
) -> WebRuntimeObservation:
    document = _canonical_json_document(
        observation.content, "web-console runtime attestation"
    )
    fields = {
        "schema_version",
        "namespace",
        "method",
        "captured_at",
        "collector_identity",
        "raw_inspect_digest",
        "raw_inspect_size_bytes",
        "raw_worker_inspect_digest",
        "raw_worker_inspect_size_bytes",
        "worker_container_id",
        "runtime",
        "mount_sources",
        "application_mount_sources_digest",
        "stable_reinspection",
        "environment_names",
        "environment_names_digest",
        "required_environment",
        "effective_web_console_configuration_digest",
        "secrets_embedded",
    }
    _exact_fields(document, fields, "web-console runtime attestation")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
        or document.get("method") != WEB_RUNTIME_ATTESTATION_METHOD
    ):
        raise SpringLaunchEvidenceError("web-console runtime attestation identity is invalid")
    _identity(document.get("collector_identity"), "web-console collector identity")
    captured = _utc_instant(
        document.get("captured_at"), "web-console runtime attestation.captured_at"
    )
    if captured > observed_at:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation cannot be captured after receipt.observed_at"
        )
    if observed_at - captured > max_age:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation is older than the allowed evidence age"
        )
    raw_digest = _digest(
        document.get("raw_inspect_digest"),
        "web-console runtime attestation.raw_inspect_digest",
    )
    raw_size = _positive_size(
        document.get("raw_inspect_size_bytes"),
        "web-console runtime attestation.raw_inspect_size_bytes",
    )
    if raw_size > MAX_JSON_BYTES:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation raw inspect exceeds the byte budget"
        )
    if document.get("raw_worker_inspect_digest") != worker_inspect_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation worker inspect digest does not match the signed raw worker evidence"
        )
    _digest(
        document.get("raw_worker_inspect_digest"),
        "web-console runtime attestation.raw_worker_inspect_digest",
    )
    raw_worker_size = _positive_size(
        document.get("raw_worker_inspect_size_bytes"),
        "web-console runtime attestation.raw_worker_inspect_size_bytes",
    )
    if raw_worker_size != worker_inspect_size_bytes or raw_worker_size > MAX_JSON_BYTES:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation worker inspect byte size mismatch"
        )
    if document.get("worker_container_id") != worker.container_id:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation worker container identity does not match raw inspect"
        )
    if document.get("stable_reinspection") is not True:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation must prove stable reinspection"
        )
    if document.get("secrets_embedded") is not False:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation.secrets_embedded must be exactly false"
        )
    mounts, project, image_reference, web_container_id, web_process_id = (
        _validate_sanitized_runtime_shape(
        document.get("runtime"), expected_image_digest=expected_image_digest
        )
    )
    _, application_mount_digest = _validate_application_mount_observations(
        document.get("mount_sources"),
        worker=worker,
        web_container_id=web_container_id,
        web_process_id=web_process_id,
        web_mount_source_digests=mounts,
    )
    if document.get("application_mount_sources_digest") != application_mount_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation application mount object digest mismatch"
        )
    raw_names = document.get("environment_names")
    if (
        not isinstance(raw_names, list)
        or any(not isinstance(name, str) for name in raw_names)
        or raw_names != sorted(raw_names)
        or len(set(raw_names)) != len(raw_names)
    ):
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation.environment_names must be a sorted unique string array"
        )
    names_digest = web_console_environment_names_digest(raw_names)
    if document.get("environment_names_digest") != names_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation environment names digest mismatch"
        )
    required = _object(
        document.get("required_environment"),
        "web-console runtime attestation.required_environment",
    )
    _exact_fields(
        required,
        {
            *WEB_CONSOLE_CONFIGURATION_ENVIRONMENT,
            *WEB_CONSOLE_DYNAMIC_ENVIRONMENT_ALLOWED,
        },
        "web-console runtime attestation.required_environment",
    )
    # Apply the same dangerous-name and exact-value policy without needing raw
    # secret values: placeholder values are sufficient for all non-required keys.
    synthetic_environment = {name: "<redacted>" for name in raw_names}
    synthetic_environment.update(required)
    checked_required, _, checked_names_digest = _validate_web_console_environment(
        synthetic_environment,
        label="web-console runtime attestation environment",
    )
    if checked_names_digest != names_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation environment inventory mismatch"
        )
    configuration_digest = web_console_configuration_digest(checked_required)
    if document.get("effective_web_console_configuration_digest") != configuration_digest:
        raise SpringLaunchEvidenceError(
            "web-console runtime attestation effective configuration digest mismatch"
        )
    return WebRuntimeObservation(
        image_digest=expected_image_digest,
        configured_image=image_reference,
        engine_secret_source_digest=mounts[
            "/run/secrets/elmos-spring-engine-hmac"
        ],
        backend_network=f"{project}_backend",
        mount_source_digests=mounts,
        environment_names_digest=names_digest,
        configuration_digest=configuration_digest,
        raw_inspect_digest=raw_digest,
        worker_inspect_digest=worker_inspect_digest,
        worker_container_id=worker.container_id,
        application_mount_sources_digest=application_mount_digest,
    )


def _validate_worker_image_artifact_attestation(
    observation: ContentObservation,
    *,
    binding: Mapping[str, Any],
    worker: ContainerRuntimeObservation,
    worker_application_artifact_digest: str,
    observed_at: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    document = _canonical_json_document(
        observation.content, "worker image artifact attestation"
    )
    fields = {
        "schema_version",
        "namespace",
        "method",
        "builder_identity",
        "build_invocation_id",
        "deployed_revision",
        "image_digest",
        "image_reference",
        "artifact_path",
        "worker_application_artifact_digest",
        "extracted_at",
        "outcome",
        "synthetic",
        "unknowns",
        "not_run",
    }
    _exact_fields(document, fields, "worker image artifact attestation")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
        or document.get("method") != WORKER_IMAGE_ARTIFACT_ATTESTATION_METHOD
    ):
        raise SpringLaunchEvidenceError(
            "worker image artifact attestation identity is invalid"
        )
    _identity(document.get("builder_identity"), "worker image artifact builder")
    _identity(document.get("build_invocation_id"), "worker image build invocation")
    expected = {
        "deployed_revision": binding["deployed_revision"],
        "image_digest": worker.image_digest,
        "image_reference": worker.configured_image,
        "artifact_path": "/app/app.jar",
        "worker_application_artifact_digest": worker_application_artifact_digest,
        "outcome": "VERIFIED",
        "synthetic": False,
        "unknowns": [],
        "not_run": [],
    }
    for name, expected_value in expected.items():
        actual = document.get(name)
        if type(actual) is not type(expected_value) or actual != expected_value:
            raise SpringLaunchEvidenceError(
                f"worker image artifact attestation binding mismatch: {name}"
            )
    extracted = _utc_instant(
        document.get("extracted_at"), "worker image artifact attestation.extracted_at"
    )
    if extracted > observed_at:
        raise SpringLaunchEvidenceError(
            "worker image artifact attestation cannot postdate receipt.observed_at"
        )
    if observed_at - extracted > max_age:
        raise SpringLaunchEvidenceError(
            "worker image artifact attestation is older than the allowed evidence age"
        )
    _reject_non_success(document, "worker image artifact attestation")
    return document


def _validate_environment_manifest(
    observation: ContentObservation,
    *,
    binding: dict[str, Any],
    roots: tuple[Path, ...],
    observed_at: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    if observation.media_type != "application/json":
        raise SpringLaunchEvidenceError(
            "binding.environment.media_type must be application/json"
        )
    document = _canonical_json_document(observation.content, "environment manifest")
    fields = {
        "schema_version",
        "namespace",
        "environment_id",
        "deployment_id",
        "environment_class",
        "provider",
        "region",
        "tenant_mode",
        "execution_plane",
        "deployed_revision",
        "launch_profile_digest",
        "artifact_digest",
        "configuration_digest",
        "application_environment_commitment_digest",
        "container_inspect",
        "web_console_runtime_attestation",
        "effective_spring_configuration_digest",
        "effective_web_console_configuration_digest",
        "web_console_environment_names_digest",
        "application_mount_sources_digest",
        "worker_image_artifact_attestation",
        "worker_application_artifact_digest",
        "network_policy_digest",
        "rootless_policy_digest",
        "runtime_image_digests",
        "captured_at",
        "secrets_embedded",
    }
    _exact_fields(document, fields, "environment manifest")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("environment manifest identity is invalid")
    for name in ("environment_id", "deployment_id", "provider", "region"):
        _identity(document.get(name), f"environment manifest.{name}")
    if document.get("environment_class") not in {"STAGING", "PRODUCTION"}:
        raise SpringLaunchEvidenceError(
            "environment manifest.environment_class must be STAGING or PRODUCTION"
        )
    if document.get("tenant_mode") != "MULTI_TENANT":
        raise SpringLaunchEvidenceError(
            "environment manifest must bind MULTI_TENANT"
        )
    if document.get("execution_plane") != "PRIVATE_ROOTLESS_RUNNER_BROKER":
        raise SpringLaunchEvidenceError(
            "environment manifest must bind PRIVATE_ROOTLESS_RUNNER_BROKER"
        )
    for name in (
        "configuration_digest",
        "application_environment_commitment_digest",
        "effective_spring_configuration_digest",
        "effective_web_console_configuration_digest",
        "web_console_environment_names_digest",
        "application_mount_sources_digest",
        "worker_application_artifact_digest",
        "network_policy_digest",
        "rootless_policy_digest",
    ):
        _digest(document.get(name), f"environment manifest.{name}")
    images = document.get("runtime_image_digests")
    if (
        not isinstance(images, dict)
        or set(images) != REQUIRED_RUNTIME_IMAGE_NAMES
        or any(not isinstance(name, str) or not name for name in images)
        or any(DIGEST_RE.fullmatch(str(value)) is None for value in images.values())
        or len(set(images.values())) != len(images)
    ):
        raise SpringLaunchEvidenceError(
            "environment manifest.runtime_image_digests must contain exactly five distinct digest-pinned application images"
        )
    captured_at = _utc_instant(
        document.get("captured_at"), "environment manifest.captured_at"
    )
    if captured_at > observed_at:
        raise SpringLaunchEvidenceError(
            "environment manifest cannot be captured after receipt.observed_at"
        )
    if observed_at - captured_at > max_age:
        raise SpringLaunchEvidenceError(
            "environment manifest capture is older than the allowed evidence age"
        )
    if document.get("secrets_embedded") is not False:
        raise SpringLaunchEvidenceError(
            "environment manifest.secrets_embedded must be exactly false"
        )
    container_inspect = _snapshot_local_json_evidence_reference(
        document.get("container_inspect"),
        roots=roots,
        label="environment manifest.container_inspect",
    )
    web_runtime_attestation = _snapshot_local_json_evidence_reference(
        document.get("web_console_runtime_attestation"),
        roots=roots,
        label="environment manifest.web_console_runtime_attestation",
    )
    image_artifact_attestation = _snapshot_local_json_evidence_reference(
        document.get("worker_image_artifact_attestation"),
        roots=roots,
        label="environment manifest.worker_image_artifact_attestation",
    )
    supporting_digests = {
        container_inspect.digest,
        web_runtime_attestation.digest,
        image_artifact_attestation.digest,
        observation.digest,
        binding["launch_profile"]["digest"],
        binding["artifact"]["digest"],
    }
    if len(supporting_digests) != 6:
        raise SpringLaunchEvidenceError(
            "worker inspect, sanitized web runtime, image artifact attestation, manifest, profile, and customer artifact bytes must be content-distinct"
        )
    worker = _spring_worker_environment_from_inspect(
        container_inspect.content,
        label="environment manifest.container_inspect.local_bytes",
        expected_image_digest=images["worker"],
    )
    worker_effective_digest = spring_worker_configuration_digest(worker.environment)
    if document.get("effective_spring_configuration_digest") != worker_effective_digest:
        raise SpringLaunchEvidenceError(
            "environment manifest effective Spring configuration digest does not match container inspect bytes"
        )
    web = _validate_web_console_runtime_attestation(
        web_runtime_attestation,
        expected_image_digest=images["web"],
        worker=worker,
        worker_inspect_digest=container_inspect.digest,
        worker_inspect_size_bytes=container_inspect.size_bytes,
        observed_at=captured_at,
        max_age=max_age,
    )
    if document.get("effective_web_console_configuration_digest") != web.configuration_digest:
        raise SpringLaunchEvidenceError(
            "environment manifest effective web-console configuration digest does not match the sanitized runtime attestation"
        )
    if document.get("web_console_environment_names_digest") != web.environment_names_digest:
        raise SpringLaunchEvidenceError(
            "environment manifest web-console environment names digest does not match the sanitized runtime attestation"
        )
    worker_application_digest = _digest(
        document.get("worker_application_artifact_digest"),
        "environment manifest.worker_application_artifact_digest",
    )
    if worker_application_digest == binding["artifact"]["digest"]:
        raise SpringLaunchEvidenceError(
            "worker application artifact digest must be distinct from the migrated customer artifact digest"
        )
    _validate_worker_image_artifact_attestation(
        image_artifact_attestation,
        binding=binding,
        worker=worker,
        worker_application_artifact_digest=worker_application_digest,
        observed_at=captured_at,
        max_age=max_age,
    )
    worker_engine_digest = _mount_source_path_digest(
        worker.mount_sources["/run/secrets/elmos-spring-engine-hmac"]
    )
    if web.engine_secret_source_digest != worker_engine_digest:
        raise SpringLaunchEvidenceError(
            "web-console and worker must consume the same application engine HMAC host source path"
        )
    if web.backend_network != worker.backend_network:
        raise SpringLaunchEvidenceError(
            "web-console and worker must share the same controlled backend network"
        )
    mount_sources_digest = web.application_mount_sources_digest
    if document.get("application_mount_sources_digest") != mount_sources_digest:
        raise SpringLaunchEvidenceError(
            "environment manifest application mount source digest does not match observed runtime mounts"
        )
    expected = {
        "deployed_revision": binding["deployed_revision"],
        "launch_profile_digest": binding["launch_profile"]["digest"],
        "artifact_digest": binding["artifact"]["digest"],
    }
    for field, expected_value in expected.items():
        if document.get(field) != expected_value:
            raise SpringLaunchEvidenceError(
                f"environment manifest binding mismatch: {field}"
            )
    _reject_non_success(document, "environment manifest")
    return document


def _validate_binding(
    value: Any,
    *,
    roots: tuple[Path, ...],
    expected_revision: str,
    expected_profile_path: Path,
    repo_root: Path,
    observed_at: datetime,
    max_age: timedelta,
) -> tuple[
    dict[str, Any],
    dict[str, ContentObservation],
    dict[str, Any],
]:
    binding = _object(value, "receipt.binding")
    _exact_fields(binding, BINDING_FIELDS, "receipt.binding")
    revision = binding.get("deployed_revision")
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise SpringLaunchEvidenceError(
            "receipt.binding.deployed_revision must be 40 lowercase hex"
        )
    if revision != expected_revision:
        raise SpringLaunchEvidenceError(
            "receipt binding deployed_revision does not match the expected repository revision"
        )
    profile = _snapshot_content_reference(
        binding.get("launch_profile"), roots, "binding.launch_profile", max_bytes=1024 * 1024
    )
    artifact = _snapshot_content_reference(
        binding.get("artifact"),
        roots,
        "binding.artifact",
        capture_content=False,
    )
    environment = _snapshot_content_reference(
        binding.get("environment"), roots, "binding.environment", max_bytes=1024 * 1024
    )
    if profile.media_type != "application/json":
        raise SpringLaunchEvidenceError(
            "binding.launch_profile.media_type must be application/json"
        )
    try:
        expected_profile = read_regular_file_once(
            expected_profile_path,
            max_bytes=1024 * 1024,
            label="expected Spring launch profile",
        )
    except (OSError, ValueError) as exc:
        raise SpringLaunchEvidenceError(
            f"expected Spring launch profile could not be read safely: {exc}"
        ) from exc
    committed_profile = _committed_file_bytes(
        repo_root,
        expected_revision,
        expected_profile_path,
        max_bytes=1024 * 1024,
        label="expected Spring launch profile",
    )
    if expected_profile != committed_profile:
        raise SpringLaunchEvidenceError(
            "expected Spring launch profile working-tree bytes do not match the expected revision"
        )
    expected_profile_digest = "sha256:" + hashlib.sha256(committed_profile).hexdigest()
    if (
        profile.digest != expected_profile_digest
        or profile.size_bytes != len(committed_profile)
    ):
        raise SpringLaunchEvidenceError(
            "receipt launch profile does not bind the expected profile bytes"
        )
    digests = {profile.digest, artifact.digest, environment.digest}
    if len(digests) != 3:
        raise SpringLaunchEvidenceError(
            "launch profile, deployed artifact, and environment manifest must be content-distinct"
        )
    environment_manifest = _validate_environment_manifest(
        environment,
        binding=binding,
        roots=roots,
        observed_at=observed_at,
        max_age=max_age,
    )
    return (
        binding,
        {
            "launch_profile": profile,
            "artifact": artifact,
            "environment": environment,
        },
        environment_manifest,
    )


def _load_controlled_index(
    value: Any,
    *,
    roots: tuple[Path, ...],
    loaded: LoadedTrust,
    receipt_id: str,
    binding_digest: str,
    observed_at: datetime,
    now: datetime,
    max_age: timedelta,
) -> ControlledIndex | None:
    if value is None:
        return None
    item = _object(value, "receipt.evidence_index")
    _exact_fields(item, {"content", "attestation"}, "receipt.evidence_index")
    content = _snapshot_content_reference(
        item.get("content"), roots, "receipt.evidence_index.content", max_bytes=MAX_JSON_BYTES
    )
    if content.media_type != "application/json":
        raise SpringLaunchEvidenceError("controlled evidence index must be application/json")
    document = _canonical_json_document(content.content, "controlled evidence index")
    _exact_fields(
        document,
        {"schema_version", "namespace", "index_id", "generated_at", "entries"},
        "controlled evidence index",
    )
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
        or document.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("controlled evidence index identity is invalid")
    index_id = _identity(document.get("index_id"), "controlled evidence index.index_id")
    generated_at = _utc_instant(
        document.get("generated_at"), "controlled evidence index.generated_at"
    )
    if generated_at > observed_at:
        raise SpringLaunchEvidenceError(
            "controlled evidence index cannot be generated after receipt.observed_at"
        )
    if observed_at - generated_at > max_age:
        raise SpringLaunchEvidenceError(
            "controlled evidence index is older than the allowed evidence age"
        )
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SpringLaunchEvidenceError(
            "controlled evidence index.entries must be non-empty"
        )
    entries: dict[str, dict[str, Any]] = {}
    entry_fields = {
        "entry_id",
        "uri",
        "digest",
        "size_bytes",
        "media_type",
        "recorded_at",
    }
    for index, raw in enumerate(raw_entries):
        entry = _object(raw, f"controlled evidence index.entries[{index}]")
        _exact_fields(entry, entry_fields, f"controlled evidence index.entries[{index}]")
        entry_id = _identity(entry.get("entry_id"), f"controlled evidence index.entries[{index}].entry_id")
        if entry_id in entries:
            raise SpringLaunchEvidenceError(
                f"duplicate controlled evidence index entry: {entry_id}"
            )
        digest = _digest(entry.get("digest"), f"controlled evidence index entry {entry_id}.digest")
        entry_size = _positive_size(
            entry.get("size_bytes"),
            f"controlled evidence index entry {entry_id}.size_bytes",
        )
        if entry_size > MAX_GATE_EVIDENCE_BYTES:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} exceeds the gate evidence byte budget"
            )
        if not isinstance(entry.get("media_type"), str) or not entry["media_type"]:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id}.media_type is invalid"
            )
        entry_uri = _immutable_uri(
            entry.get("uri"), digest, f"controlled evidence index entry {entry_id}.uri"
        )
        if urlparse(entry_uri).scheme == "file":
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} must use immutable remote or CAS identity"
            )
        recorded_at = _utc_instant(
            entry.get("recorded_at"), f"controlled evidence index entry {entry_id}.recorded_at"
        )
        if recorded_at > generated_at:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} was recorded after index generation"
            )
        if observed_at - recorded_at > max_age:
            raise SpringLaunchEvidenceError(
                f"controlled evidence index entry {entry_id} is older than the allowed evidence age"
            )
        entries[entry_id] = entry
    bindings = {
        "role": INDEX_AUTHORITY_ROLE,
        "receipt_id": receipt_id,
        "binding_digest": binding_digest,
        "index_id": index_id,
        "index_content_digest": content.digest,
        "index_content_size_bytes": content.size_bytes,
        "outcome": "INDEX_AUTHENTICATED",
        "synthetic": False,
        "unknowns": [],
        "not_run": [],
    }
    attestation = _verify_envelope(
        loaded,
        item.get("attestation"),
        role=INDEX_AUTHORITY_ROLE,
        expected_fields=INDEX_PAYLOAD_FIELDS,
        bindings=bindings,
        now=now,
    )
    if attestation.issued_at < observed_at:
        raise SpringLaunchEvidenceError(
            "controlled evidence index attestation predates receipt.observed_at"
        )
    return ControlledIndex(
        index_id=index_id,
        content_digest=content.digest,
        entries=entries,
        attestation=attestation,
    )


def _verify_evidence_reference(
    value: Any,
    *,
    roots: tuple[Path, ...],
    controlled_index: ControlledIndex | None,
    label: str,
) -> dict[str, Any]:
    reference = _object(value, label)
    _exact_fields(reference, EVIDENCE_REFERENCE_FIELDS, label)
    digest = _digest(reference.get("digest"), f"{label}.digest")
    size = _positive_size(reference.get("size_bytes"), f"{label}.size_bytes")
    media_type = reference.get("media_type")
    if not isinstance(media_type, str) or not media_type:
        raise SpringLaunchEvidenceError(f"{label}.media_type is invalid")
    uri = _immutable_uri(reference.get("uri"), digest, f"{label}.uri")
    verification = _object(reference.get("verification"), f"{label}.verification")
    mode = verification.get("mode")
    if mode == "LOCAL_BYTES":
        _exact_fields(verification, {"mode", "local_uri"}, f"{label}.verification")
        local = {
            "uri": verification.get("local_uri"),
            "digest": digest,
            "size_bytes": size,
            "media_type": media_type,
        }
        observation = _snapshot_content_reference(
            local,
            roots,
            f"{label}.local_bytes",
            max_bytes=MAX_GATE_EVIDENCE_BYTES,
            capture_content=False,
        )
        return {
            "uri": uri,
            "digest": observation.digest,
            "size_bytes": observation.size_bytes,
            "media_type": media_type,
            "verification_mode": mode,
        }
    if mode == "CONTROLLED_INDEX":
        _exact_fields(
            verification,
            {"mode", "entry_id", "entry_digest"},
            f"{label}.verification",
        )
        if controlled_index is None:
            raise SpringLaunchEvidenceError(
                f"{label} requires a signed controlled evidence index"
            )
        if urlparse(uri).scheme == "file":
            raise SpringLaunchEvidenceError(
                f"{label} CONTROLLED_INDEX mode cannot authorize a file URI"
            )
        entry_id = _identity(verification.get("entry_id"), f"{label}.verification.entry_id")
        entry_digest = _digest(
            verification.get("entry_digest"), f"{label}.verification.entry_digest"
        )
        entry = controlled_index.entries.get(entry_id)
        if entry is None:
            raise SpringLaunchEvidenceError(
                f"{label} controlled index entry is missing"
            )
        if canonical_digest(entry) != entry_digest:
            raise SpringLaunchEvidenceError(
                f"{label} controlled index entry digest mismatch"
            )
        expected = {
            "uri": uri,
            "digest": digest,
            "size_bytes": size,
            "media_type": media_type,
        }
        if size > MAX_GATE_EVIDENCE_BYTES:
            raise SpringLaunchEvidenceError(
                f"{label} exceeds the gate evidence byte budget"
            )
        for field, expected_value in expected.items():
            if entry.get(field) != expected_value:
                raise SpringLaunchEvidenceError(
                    f"{label} controlled index binding mismatch: {field}"
                )
        return {
            **expected,
            "verification_mode": mode,
            "index_id": controlled_index.index_id,
            "entry_id": entry_id,
        }
    raise SpringLaunchEvidenceError(
        f"{label}.verification.mode must be LOCAL_BYTES or CONTROLLED_INDEX"
    )


def receipt_digest(value: dict[str, Any]) -> str:
    """Return the canonical digest of all receipt fields except receipt_digest."""

    subject = dict(value)
    subject.pop("receipt_digest", None)
    return canonical_digest(subject)


def spring_environment_configuration_digest(
    environment: Mapping[str, str],
) -> str:
    """Digest the effective Spring launch configuration without secret bytes.

    The contract is canonical JSON over every exact key in
    :data:`SPRING_CONFIGURATION_ENV_KEYS`; absent keys normalize to the empty
    string.  Secret *host paths* are configuration and therefore included, but
    this helper never opens them and never includes their contents.  Callers
    must run the ordinary secret-file validation separately.
    """

    values: dict[str, str] = {}
    for name in SPRING_CONFIGURATION_ENV_KEYS:
        raw = environment.get(name, "")
        if not isinstance(raw, str):
            raise SpringLaunchEvidenceError(
                f"effective Spring environment value {name} must be a string"
            )
        values[name] = raw
    return canonical_digest(
        {
            "schema_version": 1,
            "namespace": NAMESPACE,
            "contract": "spring-launch-effective-environment-v1",
            "values": values,
        }
    )


def _register_signer(
    verified: VerifiedEnvelope,
    *,
    record_ids: set[str],
    key_owners: dict[str, tuple[str, str]],
    public_key_owners: dict[str, tuple[str, str]],
    actor_roles: dict[str, str],
    organization_roles: dict[str, str],
) -> None:
    record_id = verified.payload["record_id"]
    if record_id in record_ids:
        raise SpringLaunchEvidenceError("signed record identities must be unique")
    record_ids.add(record_id)
    prior_actor_role = actor_roles.setdefault(verified.actor_id, verified.role)
    if prior_actor_role != verified.role:
        raise SpringLaunchEvidenceError(
            "one actor identity cannot occupy multiple receipt signing roles"
        )
    prior_organization_role = organization_roles.setdefault(
        verified.organization_id, verified.role
    )
    if prior_organization_role != verified.role:
        raise SpringLaunchEvidenceError(
            "one organization cannot occupy multiple receipt signing roles"
        )
    owner = (verified.actor_id, verified.role)
    prior_key_owner = key_owners.setdefault(verified.key_id, owner)
    if prior_key_owner != owner:
        raise SpringLaunchEvidenceError("signing key identity was reused across roles")
    prior_public_owner = public_key_owners.setdefault(
        verified.public_key_digest, owner
    )
    if prior_public_owner != owner:
        raise SpringLaunchEvidenceError(
            "public-key material was reused across actors or roles"
        )


def verify_spring_launch_receipt(
    value: Any,
    *,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    expected_revision: str | None = None,
    expected_profile_path: Path = PROFILE,
    expected_trust_store_digest: str | None = None,
    expected_environment_id: str | None = None,
    expected_deployment_id: str | None = None,
    expected_provider: str | None = None,
    expected_region: str | None = None,
    expected_environment_class: str | None = None,
    expected_configuration_digest: str | None = None,
    expected_application_environment_commitment_digest: str | None = None,
    expected_effective_spring_configuration_digest: str | None = None,
    expected_effective_web_console_configuration_digest: str | None = None,
    expected_web_console_environment_names_digest: str | None = None,
    expected_application_mount_sources_digest: str | None = None,
    expected_worker_application_artifact_digest: str | None = None,
    repo_root: Path = ROOT,
    now: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> dict[str, Any]:
    """Authenticate a complete receipt without changing any launch status."""

    receipt = _object(value, "receipt")
    _exact_fields(receipt, TOP_LEVEL_FIELDS, "receipt")
    if (
        type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
        or receipt.get("namespace") != NAMESPACE
    ):
        raise SpringLaunchEvidenceError("receipt identity is invalid")
    if receipt.get("business_line") != BUSINESS_LINE:
        raise SpringLaunchEvidenceError("receipt business_line is invalid")
    if receipt.get("route_id") != ROUTE_ID:
        raise SpringLaunchEvidenceError("receipt route_id is invalid")
    receipt_id = _identity(receipt.get("receipt_id"), "receipt.receipt_id")
    _reject_non_success(receipt, "receipt")
    observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed_now.utcoffset() != timedelta(0):
        raise SpringLaunchEvidenceError("verification clock must be UTC")
    if max_age <= timedelta(0):
        raise SpringLaunchEvidenceError("max_age must be positive")
    observed_at = _utc_instant(receipt.get("observed_at"), "receipt.observed_at")
    if observed_at > observed_now:
        raise SpringLaunchEvidenceError("receipt.observed_at cannot be in the future")
    if observed_now - observed_at > max_age:
        raise SpringLaunchEvidenceError("receipt external evidence is stale")
    roots = _approved_roots(evidence_roots)
    revision = _expected_revision(expected_revision, repo_root)
    binding, primary, environment_manifest = _validate_binding(
        receipt.get("binding"),
        roots=roots,
        expected_revision=revision,
        expected_profile_path=expected_profile_path,
        repo_root=repo_root,
        observed_at=observed_at,
        max_age=max_age,
    )
    expected_environment_values = {
        "environment_id": expected_environment_id,
        "deployment_id": expected_deployment_id,
        "provider": expected_provider,
        "region": expected_region,
        "environment_class": expected_environment_class,
        "configuration_digest": expected_configuration_digest,
        "application_environment_commitment_digest": (
            expected_application_environment_commitment_digest
        ),
        "effective_spring_configuration_digest": (
            expected_effective_spring_configuration_digest
        ),
        "effective_web_console_configuration_digest": (
            expected_effective_web_console_configuration_digest
        ),
        "web_console_environment_names_digest": (
            expected_web_console_environment_names_digest
        ),
        "application_mount_sources_digest": (
            expected_application_mount_sources_digest
        ),
        "worker_application_artifact_digest": (
            expected_worker_application_artifact_digest
        ),
    }
    for field, expected_value in expected_environment_values.items():
        if expected_value is None:
            continue
        if field.endswith("_digest"):
            _digest(expected_value, f"expected {field}")
        elif field == "environment_class":
            if expected_value not in {"STAGING", "PRODUCTION"}:
                raise SpringLaunchEvidenceError(
                    "expected environment class must be STAGING or PRODUCTION"
                )
        else:
            _identity(expected_value, f"expected {field}")
        if environment_manifest[field] != expected_value:
            raise SpringLaunchEvidenceError(
                f"signed environment manifest does not match expected {field}"
            )
    binding_digest = canonical_digest(binding)
    if receipt.get("binding_digest") != binding_digest:
        raise SpringLaunchEvidenceError("receipt.binding_digest mismatch")
    expected_receipt_digest = receipt_digest(receipt)
    if receipt.get("receipt_digest") != expected_receipt_digest:
        raise SpringLaunchEvidenceError("receipt.receipt_digest mismatch")

    principals_raw = _object(receipt.get("principals"), "receipt.principals")
    _exact_fields(
        principals_raw,
        {"execution", "independent_verifier", "independent_reviewer"},
        "receipt.principals",
    )
    principals = {
        name: _principal(principals_raw[name], f"receipt.principals.{name}")
        for name in ("execution", "independent_verifier", "independent_reviewer")
    }
    if len({item["actor_id"] for item in principals.values()}) != 3:
        raise SpringLaunchEvidenceError(
            "execution, verifier, and reviewer actor identities must be distinct"
        )
    if len({item["organization_id"] for item in principals.values()}) != 3:
        raise SpringLaunchEvidenceError(
            "execution, verifier, and reviewer organizations must be distinct"
        )

    if isinstance(trust_store, Path):
        loaded = _load_trust(trust_store, evidence_roots=roots)
    else:
        loaded = trust_store
        _validate_trust_store_path(loaded.store.path, roots)
    if expected_trust_store_digest is not None:
        _digest(expected_trust_store_digest, "expected trust store digest")
        if loaded.store.digest != expected_trust_store_digest:
            raise SpringLaunchEvidenceError(
                "loaded trust store does not match expected trust store digest"
            )
    controlled_index = _load_controlled_index(
        receipt.get("evidence_index"),
        roots=roots,
        loaded=loaded,
        receipt_id=receipt_id,
        binding_digest=binding_digest,
        observed_at=observed_at,
        now=observed_now,
        max_age=max_age,
    )

    raw_gates = receipt.get("gates")
    if not isinstance(raw_gates, list) or len(raw_gates) != len(GATE_IDS):
        raise SpringLaunchEvidenceError("receipt.gates must contain nine exact gates")
    evidence_subject_gates: list[dict[str, Any]] = []
    evidence_observations: list[dict[str, Any]] = []
    for index, expected_gate_id in enumerate(GATE_IDS):
        gate = _object(raw_gates[index], f"receipt.gates[{index}]")
        _exact_fields(
            gate,
            {"id", "status", "evidence", "execution_attestation", "verification_attestation"},
            f"receipt.gates[{index}]",
        )
        if gate.get("id") != expected_gate_id:
            raise SpringLaunchEvidenceError(
                f"receipt.gates[{index}] must be {expected_gate_id}"
            )
        if gate.get("status") != "PASSED_EXTERNAL":
            raise SpringLaunchEvidenceError(
                f"external gate {expected_gate_id} is not PASSED_EXTERNAL"
            )
        observed = _verify_evidence_reference(
            gate.get("evidence"),
            roots=roots,
            controlled_index=controlled_index,
            label=f"receipt.gates[{index}].evidence",
        )
        evidence_subject_gates.append(
            {
                "id": expected_gate_id,
                "status": "PASSED_EXTERNAL",
                "evidence": gate["evidence"],
            }
        )
        evidence_observations.append(observed)
    evidence_digests = [item["digest"] for item in evidence_observations]
    if len(set(evidence_digests)) != len(GATE_IDS):
        raise SpringLaunchEvidenceError(
            "all nine external gates must bind content-distinct evidence"
        )
    primary_digests = {item.digest for item in primary.values()}
    primary_digests.update(
        {
            environment_manifest["container_inspect"]["digest"],
            environment_manifest["web_console_runtime_attestation"]["digest"],
            environment_manifest["worker_image_artifact_attestation"]["digest"],
        }
    )
    if primary_digests.intersection(evidence_digests):
        raise SpringLaunchEvidenceError(
            "gate evidence must be distinct from profile, artifact, and environment bytes"
        )
    evidence_uris = [item["uri"] for item in evidence_observations]
    if len(set(evidence_uris)) != len(evidence_uris):
        raise SpringLaunchEvidenceError("all nine external gates must use distinct evidence URIs")
    used_index = any(
        item["verification_mode"] == "CONTROLLED_INDEX"
        for item in evidence_observations
    )
    if used_index != (controlled_index is not None):
        raise SpringLaunchEvidenceError(
            "receipt.evidence_index must exist exactly when controlled-index evidence is used"
        )
    evidence_set_digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "observed_at": receipt["observed_at"],
            "controlled_index_content_digest": (
                controlled_index.content_digest if controlled_index is not None else None
            ),
            "gates": evidence_subject_gates,
        }
    )

    record_ids: set[str] = set()
    key_owners: dict[str, tuple[str, str]] = {}
    public_key_owners: dict[str, tuple[str, str]] = {}
    actor_roles: dict[str, str] = {}
    organization_roles: dict[str, str] = {}
    signed_records: list[VerifiedEnvelope] = []
    if controlled_index is not None:
        if (
            controlled_index.attestation.actor_id
            in {item["actor_id"] for item in principals.values()}
            or controlled_index.attestation.organization_id
            in {item["organization_id"] for item in principals.values()}
        ):
            raise SpringLaunchEvidenceError(
                "controlled-index authority must be separate from execution and assurance principals"
            )
        _register_signer(
            controlled_index.attestation,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        signed_records.append(controlled_index.attestation)

    gate_attestation_subject: list[dict[str, str]] = []
    latest_gate_signature = observed_at
    for index, gate_id in enumerate(GATE_IDS):
        gate = raw_gates[index]
        observed = evidence_observations[index]
        common = {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "gate_id": gate_id,
            "evidence_uri": observed["uri"],
            "evidence_digest": observed["digest"],
            "evidence_size_bytes": observed["size_bytes"],
            "outcome": "PASSED_EXTERNAL",
            "evidence_class": "EXTERNAL_NON_SYNTHETIC",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
        }
        execution = _verify_envelope(
            loaded,
            gate.get("execution_attestation"),
            role=EXECUTOR_ROLE,
            expected_fields=EXECUTION_PAYLOAD_FIELDS,
            bindings={"role": EXECUTOR_ROLE, **common},
            now=observed_now,
            expected_principal=principals["execution"],
        )
        if execution.issued_at < observed_at:
            raise SpringLaunchEvidenceError(
                f"{gate_id} execution attestation predates receipt.observed_at"
            )
        _register_signer(
            execution,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        verification_bindings = {
            "role": VERIFIER_ROLE,
            **common,
            "execution_record_id": execution.payload["record_id"],
            "execution_payload_digest": execution.payload_digest,
        }
        verification = _verify_envelope(
            loaded,
            gate.get("verification_attestation"),
            role=VERIFIER_ROLE,
            expected_fields=VERIFICATION_PAYLOAD_FIELDS,
            bindings=verification_bindings,
            now=observed_now,
            expected_principal=principals["independent_verifier"],
        )
        if verification.issued_at < execution.issued_at:
            raise SpringLaunchEvidenceError(
                f"{gate_id} verification attestation predates execution attestation"
            )
        _register_signer(
            verification,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        signed_records.extend((execution, verification))
        latest_gate_signature = max(latest_gate_signature, verification.issued_at)
        gate_attestation_subject.append(
            {
                "gate_id": gate_id,
                "execution_envelope_digest": execution.envelope_digest,
                "verification_envelope_digest": verification.envelope_digest,
            }
        )

    core_actor_ids = {item["actor_id"] for item in principals.values()}
    core_organization_ids = {item["organization_id"] for item in principals.values()}
    approvals_raw = receipt.get("approvals")
    if not isinstance(approvals_raw, list) or len(approvals_raw) < 2:
        raise SpringLaunchEvidenceError("at least two signed external approvals are required")
    approvals: list[VerifiedEnvelope] = []
    approval_scopes: set[str] = set()
    for index, raw in enumerate(approvals_raw):
        envelope = _object(raw, f"receipt.approvals[{index}]")
        payload = _object(envelope.get("payload"), f"receipt.approvals[{index}].payload")
        scope = payload.get("approval_scope")
        if scope not in {"RELEASE_AUTHORIZATION", "RISK_ACCEPTANCE"}:
            raise SpringLaunchEvidenceError(
                "approval_scope must be RELEASE_AUTHORIZATION or RISK_ACCEPTANCE"
            )
        verified = _verify_envelope(
            loaded,
            envelope,
            role=APPROVER_ROLE,
            expected_fields=APPROVAL_PAYLOAD_FIELDS,
            bindings={
                "role": APPROVER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "approval_scope": scope,
                "outcome": "APPROVED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
            now=observed_now,
        )
        if verified.issued_at < latest_gate_signature:
            raise SpringLaunchEvidenceError(
                "external approval predates completion of gate verification"
            )
        if verified.actor_id in core_actor_ids:
            raise SpringLaunchEvidenceError(
                "external approvers must be separate from execution, verifier, and reviewer"
            )
        if verified.organization_id in core_organization_ids:
            raise SpringLaunchEvidenceError(
                "external approval organizations must be separate from execution and assurance organizations"
            )
        _register_signer(
            verified,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        approvals.append(verified)
        approval_scopes.add(scope)
    if len({item.actor_id for item in approvals}) < 2:
        raise SpringLaunchEvidenceError("external approvals require two distinct actors")
    if len({item.organization_id for item in approvals}) < 2:
        raise SpringLaunchEvidenceError(
            "external approvals require two distinct organizations"
        )
    if approval_scopes != {"RELEASE_AUTHORIZATION", "RISK_ACCEPTANCE"}:
        raise SpringLaunchEvidenceError(
            "external approvals must cover release authorization and risk acceptance"
        )

    partners_raw = receipt.get("design_partner_acceptances")
    if not isinstance(partners_raw, list) or len(partners_raw) < 2:
        raise SpringLaunchEvidenceError(
            "at least two signed design-partner acceptances are required"
        )
    partners: list[VerifiedEnvelope] = []
    for index, raw in enumerate(partners_raw):
        envelope = _object(raw, f"receipt.design_partner_acceptances[{index}]")
        payload = _object(
            envelope.get("payload"),
            f"receipt.design_partner_acceptances[{index}].payload",
        )
        partner_organization = payload.get("partner_organization_id")
        verified = _verify_envelope(
            loaded,
            envelope,
            role=DESIGN_PARTNER_ROLE,
            expected_fields=PARTNER_PAYLOAD_FIELDS,
            bindings={
                "role": DESIGN_PARTNER_ROLE,
                "receipt_id": receipt_id,
                "binding_digest": binding_digest,
                "evidence_set_digest": evidence_set_digest,
                "partner_organization_id": partner_organization,
                "outcome": "ACCEPTED",
                "synthetic": False,
                "unknowns": [],
                "not_run": [],
            },
            now=observed_now,
        )
        if partner_organization != verified.organization_id:
            raise SpringLaunchEvidenceError(
                "design-partner organization must match its trusted signing identity"
            )
        if verified.issued_at < latest_gate_signature:
            raise SpringLaunchEvidenceError(
                "design-partner acceptance predates completion of gate verification"
            )
        if verified.actor_id in core_actor_ids or verified.organization_id in core_organization_ids:
            raise SpringLaunchEvidenceError(
                "design partners must be separate from execution and assurance principals"
            )
        _register_signer(
            verified,
            record_ids=record_ids,
            key_owners=key_owners,
            public_key_owners=public_key_owners,
            actor_roles=actor_roles,
            organization_roles=organization_roles,
        )
        partners.append(verified)
    if len({item.actor_id for item in partners}) < 2:
        raise SpringLaunchEvidenceError(
            "design-partner acceptances require two distinct actors"
        )
    partner_organizations = {item.organization_id for item in partners}
    if len(partner_organizations) < 2:
        raise SpringLaunchEvidenceError(
            "design-partner acceptances require two distinct organizations"
        )

    review_subject_digest = canonical_digest(
        {
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "controlled_index_attestation_digest": (
                controlled_index.attestation.envelope_digest
                if controlled_index is not None
                else None
            ),
            "gate_attestations": gate_attestation_subject,
            "approval_envelope_digests": sorted(
                item.envelope_digest for item in approvals
            ),
            "design_partner_envelope_digests": sorted(
                item.envelope_digest for item in partners
            ),
        }
    )
    review = _verify_envelope(
        loaded,
        receipt.get("independent_review"),
        role=REVIEWER_ROLE,
        expected_fields=REVIEW_PAYLOAD_FIELDS,
        bindings={
            "role": REVIEWER_ROLE,
            "receipt_id": receipt_id,
            "binding_digest": binding_digest,
            "evidence_set_digest": evidence_set_digest,
            "review_subject_digest": review_subject_digest,
            "outcome": "REVIEWED",
            "synthetic": False,
            "unknowns": [],
            "not_run": [],
        },
        now=observed_now,
        expected_principal=principals["independent_reviewer"],
    )
    latest_endorsement = max(
        [latest_gate_signature]
        + [item.issued_at for item in approvals]
        + [item.issued_at for item in partners]
        + (
            [controlled_index.attestation.issued_at]
            if controlled_index is not None
            else []
        )
    )
    if review.issued_at < latest_endorsement:
        raise SpringLaunchEvidenceError(
            "independent review predates a gate, approval, or partner endorsement"
        )
    _register_signer(
        review,
        record_ids=record_ids,
        key_owners=key_owners,
        public_key_owners=public_key_owners,
        actor_roles=actor_roles,
        organization_roles=organization_roles,
    )
    signed_records.append(review)

    return {
        "schema_version": 1,
        "namespace": NAMESPACE,
        "receipt_id": receipt_id,
        "business_line": BUSINESS_LINE,
        "route_id": ROUTE_ID,
        "source_revision": binding["deployed_revision"],
        "launch_profile_sha256": primary["launch_profile"].digest.removeprefix("sha256:"),
        "artifact_sha256": primary["artifact"].digest.removeprefix("sha256:"),
        "environment_digest": primary["environment"].digest.removeprefix("sha256:"),
        "environment_id": environment_manifest["environment_id"],
        "deployment_id": environment_manifest["deployment_id"],
        "environment_class": environment_manifest["environment_class"],
        "provider": environment_manifest["provider"],
        "region": environment_manifest["region"],
        "configuration_digest": environment_manifest["configuration_digest"],
        "application_environment_commitment_digest": environment_manifest[
            "application_environment_commitment_digest"
        ],
        "container_inspect_digest": environment_manifest["container_inspect"][
            "digest"
        ],
        "web_console_runtime_attestation_digest": environment_manifest[
            "web_console_runtime_attestation"
        ]["digest"],
        "worker_image_artifact_attestation_digest": environment_manifest[
            "worker_image_artifact_attestation"
        ]["digest"],
        "effective_spring_configuration_digest": environment_manifest[
            "effective_spring_configuration_digest"
        ],
        "effective_web_console_configuration_digest": environment_manifest[
            "effective_web_console_configuration_digest"
        ],
        "web_console_environment_names_digest": environment_manifest[
            "web_console_environment_names_digest"
        ],
        "application_mount_sources_digest": environment_manifest[
            "application_mount_sources_digest"
        ],
        "worker_application_artifact_digest": environment_manifest[
            "worker_application_artifact_digest"
        ],
        "network_policy_digest": environment_manifest["network_policy_digest"],
        "rootless_policy_digest": environment_manifest["rootless_policy_digest"],
        "binding_digest": binding_digest,
        "evidence_set_digest": evidence_set_digest,
        "review_subject_digest": review_subject_digest,
        "receipt_digest": expected_receipt_digest,
        "trust_store_digest": loaded.store.digest,
        "observed_at": receipt["observed_at"],
        "verified_gate_ids": list(GATE_IDS),
        "execution_identity": principals["execution"]["actor_id"],
        "independent_verifier": principals["independent_verifier"]["actor_id"],
        "independent_reviewer": principals["independent_reviewer"]["actor_id"],
        "approved_by": sorted(item.actor_id for item in approvals),
        "design_partner_organizations": sorted(partner_organizations),
        "evidence_status": "VERIFIED_EXTERNAL_RECEIPT",
        "external_evidence_intake": "VALIDATED_NOT_CERTIFIED",
        "certification": "NOT_CERTIFIED",
        "certification_promoted": False,
        "synthetic_evidence_can_promote": False,
    }


def verify_spring_launch_receipt_file(
    path: Path,
    *,
    trust_store: Path | LoadedTrust,
    evidence_roots: Iterable[Path],
    expected_revision: str | None = None,
    expected_profile_path: Path = PROFILE,
    expected_trust_store_digest: str | None = None,
    expected_environment_id: str | None = None,
    expected_deployment_id: str | None = None,
    expected_provider: str | None = None,
    expected_region: str | None = None,
    expected_environment_class: str | None = None,
    expected_configuration_digest: str | None = None,
    expected_application_environment_commitment_digest: str | None = None,
    expected_effective_spring_configuration_digest: str | None = None,
    expected_effective_web_console_configuration_digest: str | None = None,
    expected_web_console_environment_names_digest: str | None = None,
    expected_application_mount_sources_digest: str | None = None,
    expected_worker_application_artifact_digest: str | None = None,
    repo_root: Path = ROOT,
    now: datetime | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> dict[str, Any]:
    """Read a bounded receipt snapshot and authenticate it."""

    roots = _approved_roots(evidence_roots)
    supplied = path.expanduser()
    if not supplied.is_absolute() or not _within(supplied, roots):
        raise SpringLaunchEvidenceError(
            "Spring launch receipt must be an absolute path below an evidence root"
        )
    snapshot = _read_secure_absolute_file(
        supplied,
        max_bytes=MAX_JSON_BYTES,
        label="Spring launch receipt",
    )
    raw = snapshot.content
    value = _load_json_bytes(raw, "Spring launch receipt")
    result = verify_spring_launch_receipt(
        value,
        trust_store=trust_store,
        evidence_roots=roots,
        expected_revision=expected_revision,
        expected_profile_path=expected_profile_path,
        expected_trust_store_digest=expected_trust_store_digest,
        expected_environment_id=expected_environment_id,
        expected_deployment_id=expected_deployment_id,
        expected_provider=expected_provider,
        expected_region=expected_region,
        expected_environment_class=expected_environment_class,
        expected_configuration_digest=expected_configuration_digest,
        expected_application_environment_commitment_digest=(
            expected_application_environment_commitment_digest
        ),
        expected_effective_spring_configuration_digest=(
            expected_effective_spring_configuration_digest
        ),
        expected_effective_web_console_configuration_digest=(
            expected_effective_web_console_configuration_digest
        ),
        expected_web_console_environment_names_digest=(
            expected_web_console_environment_names_digest
        ),
        expected_application_mount_sources_digest=(
            expected_application_mount_sources_digest
        ),
        expected_worker_application_artifact_digest=(
            expected_worker_application_artifact_digest
        ),
        repo_root=repo_root,
        now=now,
        max_age=max_age,
    )
    return {
        **result,
        "receipt_file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "receipt_file_size_bytes": len(raw),
    }


def content_reference(
    path: Path,
    *,
    evidence_roots: Iterable[Path],
    media_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Create a digest reference for existing bytes below an approved root."""

    roots = _approved_roots(evidence_roots)
    supplied = Path(os.path.abspath(path.expanduser()))
    try:
        resolved = supplied.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError("reference file does not exist") from exc
    if supplied != resolved:
        raise SpringLaunchEvidenceError(
            "reference file path must be canonical and contain no symlink"
        )
    opened_local = _open_local_file(resolved.as_uri(), roots, "reference file")
    # Stream once to derive the digest, then use the ordinary verifier on future
    # intake.  This command never copies, uploads, or signs the source bytes.
    descriptor = opened_local.descriptor
    digest_value = hashlib.sha256()
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size <= 0
            or opened.st_size > MAX_CONTENT_BYTES
        ):
            raise SpringLaunchEvidenceError("reference file is invalid or exceeds the byte budget")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest_value.update(chunk)
        completed = os.fstat(descriptor)
        path_after = os.stat(
            opened_local.filename,
            dir_fd=opened_local.parent_descriptor,
            follow_symlinks=False,
        )
    finally:
        os.close(descriptor)
        os.close(opened_local.parent_descriptor)
    if (
        _stat_identity(opened) != _stat_identity(completed)
        or _stat_identity(path_after) != _stat_identity(completed)
    ):
        raise SpringLaunchEvidenceError("reference file changed while being hashed")
    return {
        "uri": opened_local.path.as_uri(),
        "digest": "sha256:" + digest_value.hexdigest(),
        "size_bytes": opened.st_size,
        "media_type": media_type,
    }


def assemble_spring_launch_receipt(
    draft: dict[str, Any],
    **verification_options: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Add only the canonical receipt digest, then verify all existing evidence.

    The input must already contain every external success claim and every signature.
    No status, payload, identity, evidence byte, or signature is synthesized here.
    """

    if "receipt_digest" in draft:
        raise SpringLaunchEvidenceError(
            "assembly draft must omit receipt_digest; use verify for a finalized receipt"
        )
    assembled = copy.deepcopy(draft)
    assembled["receipt_digest"] = receipt_digest(assembled)
    result = verify_spring_launch_receipt(assembled, **verification_options)
    return assembled, result


def _load_cli_json(path: Path, label: str) -> dict[str, Any]:
    snapshot = _read_secure_absolute_file(
        path,
        max_bytes=MAX_JSON_BYTES,
        label=label,
    )
    return _load_json_bytes(snapshot.content, label)


def _write_new_owner_only(path: Path, content: bytes) -> None:
    supplied = path.expanduser()
    if not supplied.is_absolute() or supplied.name in {"", ".", ".."}:
        raise SpringLaunchEvidenceError("output path must be an absolute file path")
    try:
        parent = supplied.parent.resolve(strict=True)
    except OSError as exc:
        raise SpringLaunchEvidenceError(
            f"output parent must be an existing directory: {exc}"
        ) from exc
    if supplied.parent != parent:
        raise SpringLaunchEvidenceError(
            "output path ancestors must be canonical and contain no symlink"
        )
    if parent == ROOT or ROOT in parent.parents:
        raise SpringLaunchEvidenceError(
            "assembled external evidence output must be outside the repository"
        )
    try:
        parent_stat = os.stat(parent, follow_symlinks=False)
    except OSError as exc:
        raise SpringLaunchEvidenceError(f"output parent is unavailable: {exc}") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise SpringLaunchEvidenceError("output parent must be a directory")
    if parent_stat.st_uid != os.getuid() or stat.S_IMODE(parent_stat.st_mode) & 0o022:
        raise SpringLaunchEvidenceError(
            "output parent must be current-account-owned and not group/other writable"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = -1
    descriptor = -1
    created_identity: tuple[int, int] | None = None
    try:
        parent_descriptor = _open_absolute_directory(parent, "output parent")
        opened_parent = os.fstat(parent_descriptor)
        if (
            opened_parent.st_dev != parent_stat.st_dev
            or opened_parent.st_ino != parent_stat.st_ino
            or opened_parent.st_uid != parent_stat.st_uid
            or opened_parent.st_mode != parent_stat.st_mode
        ):
            raise SpringLaunchEvidenceError("output parent changed while it was opened")
        descriptor = os.open(
            supplied.name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
        output_stat = os.fstat(descriptor)
        created_identity = (output_stat.st_dev, output_stat.st_ino)
        if (
            not stat.S_ISREG(output_stat.st_mode)
            or output_stat.st_uid != os.getuid()
            or output_stat.st_nlink != 1
            or stat.S_IMODE(output_stat.st_mode) != 0o600
        ):
            raise SpringLaunchEvidenceError(
                "assembled output must be a new owner-only regular file"
            )
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise SpringLaunchEvidenceError(
                    "assembled output write made no forward progress"
                )
            offset += written
        os.fsync(descriptor)
        completed = os.fstat(descriptor)
        path_after = os.stat(
            supplied.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            (completed.st_dev, completed.st_ino) != created_identity
            or (path_after.st_dev, path_after.st_ino) != created_identity
            or completed.st_size != len(content)
            or path_after.st_size != len(content)
            or stat.S_IMODE(completed.st_mode) != 0o600
            or stat.S_IMODE(path_after.st_mode) != 0o600
        ):
            raise SpringLaunchEvidenceError(
                "assembled output identity or size changed while it was written"
            )
        os.fsync(parent_descriptor)
    except BaseException as exc:
        if parent_descriptor >= 0 and descriptor >= 0:
            try:
                if created_identity is None:
                    current = os.fstat(descriptor)
                    created_identity = (current.st_dev, current.st_ino)
                entry = os.stat(
                    supplied.name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if (entry.st_dev, entry.st_ino) == created_identity:
                    os.unlink(supplied.name, dir_fd=parent_descriptor)
                    os.fsync(parent_descriptor)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise SpringLaunchEvidenceError(
                f"output must be a new file in an existing safe directory: {exc}"
            ) from exc
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _bounded_docker_inspect(
    docker_host: str, container: str, *, timeout_seconds: float = 20.0
) -> bytes:
    """Read one Docker inspect response into bounded memory only."""

    process: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(
            [
                "docker",
                "--host",
                docker_host,
                "inspect",
                "--type",
                "container",
                container,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:
            raise SpringLaunchEvidenceError("Docker inspect stdout was not created")
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout_seconds
        chunks: list[bytes] = []
        total = 0
        reached_eof = False
        while not reached_eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SpringLaunchEvidenceError("live Docker inspect timed out")
            events = selector.select(remaining)
            if not events:
                raise SpringLaunchEvidenceError("live Docker inspect timed out")
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                if not chunk:
                    reached_eof = True
                    break
                total += len(chunk)
                if total > MAX_JSON_BYTES:
                    raise SpringLaunchEvidenceError(
                        "live Docker inspect exceeds the byte budget"
                    )
                chunks.append(chunk)
        remaining = max(0.001, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        if return_code != 0:
            raise SpringLaunchEvidenceError("live Docker inspect failed closed")
        content = b"".join(chunks)
        if not content:
            raise SpringLaunchEvidenceError("live Docker inspect returned no bytes")
        return content
    except (OSError, subprocess.SubprocessError) as exc:
        raise SpringLaunchEvidenceError(
            "live Docker inspect could not be executed safely"
        ) from exc
    finally:
        selector.close()
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.SubprocessError:
                pass


def _verification_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "trust_store": args.trust_store,
        "evidence_roots": args.evidence_root,
        "expected_revision": args.expected_revision,
        "expected_profile_path": args.expected_profile,
        "expected_trust_store_digest": args.expected_trust_store_digest,
        "expected_environment_id": args.expected_environment_id,
        "expected_deployment_id": args.expected_deployment_id,
        "expected_provider": args.expected_provider,
        "expected_region": args.expected_region,
        "expected_environment_class": args.expected_environment_class,
        "expected_configuration_digest": args.expected_configuration_digest,
        "expected_application_environment_commitment_digest": (
            args.expected_application_environment_commitment_digest
        ),
        "expected_effective_spring_configuration_digest": (
            args.expected_effective_spring_configuration_digest
        ),
        "expected_effective_web_console_configuration_digest": (
            args.expected_effective_web_console_configuration_digest
        ),
        "expected_web_console_environment_names_digest": (
            args.expected_web_console_environment_names_digest
        ),
        "expected_application_mount_sources_digest": (
            args.expected_application_mount_sources_digest
        ),
        "expected_worker_application_artifact_digest": (
            args.expected_worker_application_artifact_digest
        ),
        "max_age": timedelta(seconds=args.max_age_seconds),
    }


def _add_verification_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trust-store", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, action="append", type=Path)
    parser.add_argument("--expected-revision")
    parser.add_argument("--expected-profile", type=Path, default=PROFILE)
    parser.add_argument("--expected-trust-store-digest", required=True)
    parser.add_argument("--expected-environment-id", required=True)
    parser.add_argument("--expected-deployment-id", required=True)
    parser.add_argument("--expected-provider", required=True)
    parser.add_argument("--expected-region", required=True)
    parser.add_argument(
        "--expected-environment-class",
        choices=("STAGING", "PRODUCTION"),
        required=True,
    )
    parser.add_argument("--expected-configuration-digest", required=True)
    parser.add_argument(
        "--expected-application-environment-commitment-digest", required=True
    )
    parser.add_argument(
        "--expected-effective-spring-configuration-digest", required=True
    )
    parser.add_argument(
        "--expected-effective-web-console-configuration-digest", required=True
    )
    parser.add_argument(
        "--expected-web-console-environment-names-digest", required=True
    )
    parser.add_argument("--expected-application-mount-sources-digest", required=True)
    parser.add_argument("--expected-worker-application-artifact-digest", required=True)
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=int(DEFAULT_MAX_AGE.total_seconds()),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    reference_parser = subparsers.add_parser(
        "reference", help="hash existing local evidence bytes"
    )
    reference_parser.add_argument("file", type=Path)
    reference_parser.add_argument("--evidence-root", required=True, action="append", type=Path)
    reference_parser.add_argument(
        "--media-type", default="application/octet-stream"
    )
    reference_parser.add_argument(
        "--gate-reference",
        action="store_true",
        help="include LOCAL_BYTES verification metadata for a gate evidence reference",
    )
    reference_parser.add_argument(
        "--advertised-uri",
        help="immutable external URI attested by the local byte snapshot",
    )

    digest_parser = subparsers.add_parser(
        "digest", help="calculate a receipt canonical digest without signing"
    )
    digest_parser.add_argument("receipt", type=Path)

    collector_parser = subparsers.add_parser(
        "collect-web-runtime",
        help="validate live docker inspect in memory and write a secret-free web runtime attestation",
    )
    collector_parser.add_argument("--container", required=True)
    collector_parser.add_argument("--worker-container", required=True)
    collector_parser.add_argument("--expected-image-digest", required=True)
    collector_parser.add_argument("--expected-worker-image-digest", required=True)
    collector_parser.add_argument("--collector-identity", required=True)
    collector_parser.add_argument("--output", required=True, type=Path)
    collector_parser.add_argument(
        "--docker-host", default="unix:///var/run/docker.sock"
    )

    verify_parser = subparsers.add_parser(
        "verify", help="authenticate a complete signed receipt"
    )
    verify_parser.add_argument("receipt", type=Path)
    _add_verification_arguments(verify_parser)

    assemble_parser = subparsers.add_parser(
        "assemble",
        help="add the canonical digest to an already complete signed draft and verify it",
    )
    assemble_parser.add_argument("draft", type=Path)
    assemble_parser.add_argument("--output", required=True, type=Path)
    _add_verification_arguments(assemble_parser)

    args = parser.parse_args(argv)
    try:
        if args.command == "reference":
            reference = content_reference(
                args.file,
                evidence_roots=args.evidence_root,
                media_type=args.media_type,
            )
            if args.advertised_uri and not args.gate_reference:
                raise SpringLaunchEvidenceError(
                    "--advertised-uri requires --gate-reference"
                )
            if args.gate_reference:
                advertised_uri = args.advertised_uri or reference["uri"]
                _immutable_uri(advertised_uri, reference["digest"], "--advertised-uri")
                reference = {
                    **reference,
                    "uri": advertised_uri,
                    "verification": {
                        "mode": "LOCAL_BYTES",
                        "local_uri": reference["uri"],
                    },
                }
            print(json.dumps(reference, indent=2, sort_keys=True))
            return 0
        if args.command == "digest":
            value = _load_cli_json(args.receipt, "Spring launch receipt")
            print(receipt_digest(value))
            return 0
        if args.command == "collect-web-runtime":
            if (
                IDENTITY_RE.fullmatch(args.container) is None
                or IDENTITY_RE.fullmatch(args.worker_container) is None
                or args.container == args.worker_container
            ):
                raise SpringLaunchEvidenceError(
                    "--container and --worker-container must be distinct exact Docker identities"
                )
            parsed_host = urlparse(args.docker_host)
            if (
                parsed_host.scheme != "unix"
                or parsed_host.netloc
                or not parsed_host.path.startswith("/")
                or parsed_host.query
                or parsed_host.fragment
            ):
                raise SpringLaunchEvidenceError(
                    "--docker-host must be an absolute unix:// socket URI"
                )
            raw_web = _bounded_docker_inspect(args.docker_host, args.container)
            raw_worker = _bounded_docker_inspect(
                args.docker_host, args.worker_container
            )

            def stable_reinspect() -> tuple[bytes, bytes]:
                return (
                    _bounded_docker_inspect(args.docker_host, args.container),
                    _bounded_docker_inspect(args.docker_host, args.worker_container),
                )

            attestation = collect_web_console_runtime_attestation(
                raw_web,
                raw_worker_inspect=raw_worker,
                expected_image_digest=args.expected_image_digest,
                expected_worker_image_digest=args.expected_worker_image_digest,
                collector_identity=args.collector_identity,
                stable_reinspect=stable_reinspect,
            )
            rendered = canonical_bytes(attestation)
            _write_new_owner_only(args.output, rendered)
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "namespace": NAMESPACE,
                        "output_digest": "sha256:"
                        + hashlib.sha256(rendered).hexdigest(),
                        "output_size_bytes": len(rendered),
                        "captured_at": attestation["captured_at"],
                        "secrets_embedded": False,
                        "external_status_created": False,
                        "signature_created": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "verify":
            result = verify_spring_launch_receipt_file(
                args.receipt, **_verification_options(args)
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "assemble":
            draft = _load_cli_json(args.draft, "Spring launch receipt draft")
            assembled, result = assemble_spring_launch_receipt(
                draft, **_verification_options(args)
            )
            rendered = (json.dumps(assembled, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
            _write_new_owner_only(args.output, rendered)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
    except (SpringLaunchEvidenceError, OSError, ValueError) as exc:
        print(f"SPRING LAUNCH EVIDENCE FAIL: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
