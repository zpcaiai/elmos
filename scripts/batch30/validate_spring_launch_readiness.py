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
SPRING_REPLAY_PATH_ENVIRONMENT = (
    "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH",
)
SPRING_ENVIRONMENT_ALLOWLIST = frozenset(
    REQUIRED_TRUE_ENVIRONMENT
    + REQUIRED_FALSE_ENVIRONMENT
    + SPRING_URL_ENVIRONMENT
    + SPRING_SECRET_PATH_ENVIRONMENT
    + SPRING_REPLAY_PATH_ENVIRONMENT
    + (
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    )
)
SPRING_ENVIRONMENT_ALLOWLIST_NORMALIZED = frozenset(
    re.sub(r"[^A-Za-z0-9]", "", name).upper()
    for name in SPRING_ENVIRONMENT_ALLOWLIST
)
FORBIDDEN_SINGLE_TENANT_ENVIRONMENT = "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID"
MAX_ENVIRONMENT_FILE_BYTES = 64 * 1024
ENVIRONMENT_ASSIGNMENT = re.compile(r"([A-Z][A-Z0-9_]*)=(.*)")
SAFE_ENVIRONMENT_VALUE = re.compile(r"[A-Za-z0-9._~:/@,+%=-]*")
EXACT_IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-]{1,199}")
SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
GIT_REVISION = re.compile(r"[0-9a-f]{40}")
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
COMPOSE_ENVIRONMENT_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)")
DANGEROUS_DEPLOYMENT_ENVIRONMENT = frozenset(
    {
        "SPRING_APPLICATION_JSON",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JAVA_OPTS",
        "JDK_JAVA_OPTIONS",
        "SERVER_SERVLET_CONTEXT_PATH",
        "SERVER_SERVLET_PATH",
        "SPRING_MVC_SERVLET_PATH",
        "SPRING_CONFIG_LOCATION",
        "SPRING_CONFIG_ADDITIONAL_LOCATION",
        "SPRING_CONFIG_IMPORT",
        "SPRING_PROFILES_ACTIVE",
        "SPRING_PROFILES_INCLUDE",
    }
)
DANGEROUS_DEPLOYMENT_ENVIRONMENT_NORMALIZED = frozenset(
    re.sub(r"[^A-Za-z0-9]", "", name).upper()
    for name in DANGEROUS_DEPLOYMENT_ENVIRONMENT
)
APPLICATION_RUNTIME_UID = 10001
APPLICATION_RUNTIME_GID = 10001
EnvironmentFileSnapshot = tuple[
    bytes,
    tuple[int, ...],
    tuple[tuple[int, ...], ...],
]


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


def stable_directory_identity(details: os.stat_result) -> tuple[int, ...]:
    """Directory identity fields unaffected by unrelated child activity."""
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
    )


def is_placeholder(value: str) -> bool:
    upper = value.upper()
    return (
        not value
        or upper in {"UNKNOWN", "TODO", "TBD", "NOT_CONFIGURED", "CHANGE_ME"}
        or upper.startswith(("CHANGE_ME_", "PLACEHOLDER_", "TODO_", "TBD_"))
    )


def https_endpoint_origin(
    value: str, *, production: bool = False
) -> tuple[str, str, int] | None:
    """Return a canonical HTTPS origin for the one approved Runner ingress."""
    if (
        not isinstance(value, str)
        or value != value.strip()
        or any(ord(character) <= 0x20 or ord(character) == 0x7F for character in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        raw_host = parsed.hostname or ""
        host = raw_host.lower()
        port = parsed.port or 443
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not host
        or raw_host.endswith(".")
        or "%" in host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or bool(parsed.query)
        or bool(parsed.fragment)
        or not 1 <= port <= 65535
        or host == "localhost"
        or host.endswith((".localhost", ".invalid"))
    ):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
        if (
            ascii_host != host
            or len(host) > 253
            or "." not in host
            or any(DNS_LABEL.fullmatch(label) is None for label in host.split("."))
        ):
            return None
        if production and any(
            host == suffix or host.endswith("." + suffix)
            for suffix in (
                "test",
                "example",
                "invalid",
                "localhost",
                "example.com",
                "example.net",
                "example.org",
            )
        ):
            return None
        return ("https", host, port)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return None
    if (
        address.is_loopback
        or address.is_unspecified
        or address.is_link_local
        or address.is_multicast
    ):
        return None
    if production and any(
        address in network
        for network in (
            ipaddress.ip_network("192.0.2.0/24"),
            ipaddress.ip_network("198.51.100.0/24"),
            ipaddress.ip_network("203.0.113.0/24"),
            ipaddress.ip_network("2001:db8::/32"),
        )
    ):
        return None
    return ("https", address.compressed, port)


def valid_https_endpoint(value: str) -> bool:
    """Accept an exact root HTTPS endpoint without credentials or local hosts."""
    return https_endpoint_origin(value) is not None


def boundary_whitespace(code_point: int) -> bool:
    """Language-neutral secret-boundary contract shared with Java and Node."""
    return (
        0x0009 <= code_point <= 0x000D
        or code_point == 0x0020
        or code_point == 0x0085
        or code_point == 0x00A0
        or code_point == 0x1680
        or 0x2000 <= code_point <= 0x200A
        or code_point in {0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF}
    )


def secure_environment_file_bytes(
    errors: list[str],
    path: Path,
    *,
    label: str,
    snapshot_out: list[EnvironmentFileSnapshot] | None = None,
) -> bytes | None:
    """Read one owner-only env file without following links or accepting path races."""
    if (
        not path.is_absolute()
        or path == Path("/")
        or path != Path(os.path.normpath(path))
    ):
        errors.append(f"{label} must use a normalized absolute non-root path")
        return None
    ancestor_metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            parent_details = parent.lstat()
            if stat.S_ISLNK(parent_details.st_mode):
                errors.append(f"{label} must not traverse symbolic-link parent directories")
                return None
            if not stat.S_ISDIR(parent_details.st_mode):
                errors.append(f"{label} parent path must contain directories only")
                return None
            if (
                parent != path.parent
                and stat.S_IMODE(parent_details.st_mode) & 0o022
                and not parent_details.st_mode & stat.S_ISVTX
            ):
                errors.append(
                    f"{label} must not traverse group/other-writable non-sticky ancestors"
                )
                return None
            if (
                parent != path.parent
                and parent_details.st_uid not in {0, os.getuid()}
            ):
                errors.append(
                    f"{label} must not traverse ancestors owned outside root/current UID"
                )
                return None
            ancestor_metadata.append((parent, stable_directory_identity(parent_details)))
        details = path.lstat()
    except OSError:
        errors.append(f"{label} is missing or unreadable")
        return None
    if stat.S_ISLNK(details.st_mode):
        errors.append(f"{label} must not be a symbolic link")
        return None
    if not stat.S_ISREG(details.st_mode):
        errors.append(f"{label} must be a regular file")
        return None
    if details.st_nlink != 1:
        errors.append(f"{label} must not be hard-linked")
        return None
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append(f"{label} is missing or unreadable")
        return None
    if resolved.is_relative_to(ROOT.resolve()):
        errors.append(f"{label} must be mounted from outside the repository")
        return None
    parent_details = path.parent.lstat()
    if (
        stat.S_IMODE(parent_details.st_mode) != 0o700
        or parent_details.st_uid != os.getuid()
        or parent_details.st_gid != os.getgid()
    ):
        errors.append(
            f"{label} parent directory must be mode 0700 and owned by the current UID/GID"
        )
        return None

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        errors.append(f"{label} is missing, unreadable, or not a regular non-symlink file")
        return None
    raw = b""
    try:
        opened_details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_details.st_mode)
            or stable_file_metadata(opened_details) != stable_file_metadata(details)
        ):
            errors.append(f"{label} changed while it was being validated")
            return None
        mode = stat.S_IMODE(opened_details.st_mode)
        if (
            opened_details.st_uid != os.getuid()
            or opened_details.st_gid != os.getgid()
        ):
            errors.append(f"{label} must be owned by the current UID/GID")
            return None
        if mode not in {0o400, 0o600}:
            errors.append(f"{label} permissions must be 0400 or 0600")
            return None
        if opened_details.st_size > MAX_ENVIRONMENT_FILE_BYTES:
            errors.append(f"{label} exceeds the 65536-byte limit")
            return None
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
        ancestors_unchanged = all(
            not stat.S_ISLNK((current := parent.lstat()).st_mode)
            and stable_directory_identity(current) == before
            for parent, before in ancestor_metadata
        )
        if (
            stable_file_metadata(after_read_details) != stable_file_metadata(opened_details)
            or stable_file_metadata(after_read_path_details) != stable_file_metadata(opened_details)
            or len(raw) != opened_details.st_size
            or not ancestors_unchanged
        ):
            errors.append(f"{label} identity or size changed while it was being read")
            return None
    except OSError:
        errors.append(f"{label} changed or became unreadable while it was being read")
        return None
    finally:
        os.close(descriptor)
    if len(raw) > MAX_ENVIRONMENT_FILE_BYTES:
        errors.append(f"{label} exceeds the 65536-byte limit")
        return None
    if snapshot_out is not None:
        snapshot_out.append(
            (
                raw,
                stable_file_metadata(after_read_details),
                tuple(before for _, before in ancestor_metadata),
            )
        )
    return raw


def parse_environment_file(
    errors: list[str],
    path: Path,
    *,
    snapshot_out: list[EnvironmentFileSnapshot] | None = None,
) -> dict[str, str]:
    """Parse a small Spring-only environment file as data, never as shell code."""
    raw = secure_environment_file_bytes(
        errors,
        path,
        label="Spring environment file",
        snapshot_out=snapshot_out,
    )
    if raw is None:
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


def normalized_environment_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", name).upper()


def dangerous_deployment_environment_name(name: str) -> bool:
    normalized = normalized_environment_name(name)
    return (
        normalized in DANGEROUS_DEPLOYMENT_ENVIRONMENT_NORMALIZED
        or normalized.startswith("SPRINGCONFIG")
        or normalized.startswith("SPRINGPROFILES")
    )


def parse_compose_environment_file(
    errors: list[str],
    path: Path,
    *,
    snapshot_out: list[EnvironmentFileSnapshot] | None = None,
) -> dict[str, str]:
    """Parse the application env-file as inert data without hashing secret bytes."""
    raw = secure_environment_file_bytes(
        errors,
        path,
        label="Compose deployment environment file",
        snapshot_out=snapshot_out,
    )
    if raw is None:
        return {}
    try:
        contents = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("Compose deployment environment file must be valid UTF-8")
        return {}
    if "\x00" in contents:
        errors.append("Compose deployment environment file must not contain NUL bytes")
        return {}

    values: dict[str, str] = {}
    seen: set[str] = set()
    for line_number, line in enumerate(contents.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.strip():
            errors.append(
                f"Compose deployment environment file line {line_number} has leading or trailing whitespace"
            )
            continue
        match = COMPOSE_ENVIRONMENT_ASSIGNMENT.fullmatch(line)
        if not match:
            errors.append(
                f"Compose deployment environment file line {line_number} must be an exact KEY=VALUE assignment"
            )
            continue
        name, value = match.groups()
        if name in seen:
            errors.append(
                f"Compose deployment environment file line {line_number} duplicates {name}"
            )
            continue
        seen.add(name)
        if "$" in value:
            errors.append(
                f"Compose deployment environment file line {line_number} contains forbidden interpolation"
            )
            continue
        if dangerous_deployment_environment_name(name):
            errors.append(
                f"Compose deployment environment file must not define dangerous override {name}"
            )
            continue
        if name in SPRING_ENVIRONMENT_ALLOWLIST and not SAFE_ENVIRONMENT_VALUE.fullmatch(value):
            errors.append(
                f"Compose deployment environment file line {line_number} has an unsafe Spring value"
            )
            continue
        values[name] = value
    return values


def validate_compose_environment_binding(
    errors: list[str],
    *,
    path: Path,
    compose_environment: Mapping[str, str],
    spring_environment: Mapping[str, str],
) -> None:
    configured_path = compose_environment.get("ELMOS_ENV_FILE", "")
    require(
        errors,
        configured_path == str(path),
        "Compose deployment environment must set ELMOS_ENV_FILE to its exact validated path",
    )
    for name in sorted(compose_environment):
        normalized = normalized_environment_name(name)
        require(
            errors,
            normalized not in SPRING_ENVIRONMENT_ALLOWLIST_NORMALIZED
            and not normalized.startswith("ELMOSSPRING"),
            f"Compose application environment must not leak Spring launch key {name} into application services",
        )
    require(
        errors,
        FORBIDDEN_SINGLE_TENANT_ENVIRONMENT not in compose_environment,
        "Compose deployment environment must not define a single-tenant Spring identity",
    )
    for name in os.environ:
        if dangerous_deployment_environment_name(name):
            errors.append(f"process environment must not define dangerous override {name}")
        normalized = normalized_environment_name(name)
        if (
            normalized in SPRING_ENVIRONMENT_ALLOWLIST_NORMALIZED
            and name not in SPRING_ENVIRONMENT_ALLOWLIST
        ):
            errors.append(
                f"process environment uses relaxed Spring launch alias {name}"
            )
        elif (
            normalized.startswith("ELMOSSPRING")
            and name not in SPRING_ENVIRONMENT_ALLOWLIST
        ):
            errors.append(
                f"process environment defines unsupported Spring launch key {name}"
            )
    if "ELMOS_ENV_FILE" in os.environ:
        require(
            errors,
            os.environ["ELMOS_ENV_FILE"] == str(path),
            "process ELMOS_ENV_FILE must equal --compose-environment-file",
        )
    for name in sorted(SPRING_ENVIRONMENT_ALLOWLIST):
        if name not in os.environ:
            continue
        require(
            errors,
            name in spring_environment,
            f"process environment must not supply missing SPRING_ENV_FILE key {name}",
        )
        if name in spring_environment:
            require(
                errors,
                os.environ[name] == spring_environment[name],
                f"process environment Spring value differs from SPRING_ENV_FILE for {name}",
            )


def deployment_configuration_digest(
    spring_configuration_digest: str,
    application_environment_commitment_digest: str,
) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "contract": "spring-launch-deployment-environment-v2",
            "spring_configuration_digest": spring_configuration_digest,
            "application_environment_commitment_digest": (
                application_environment_commitment_digest
            ),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def effective_environment(file_values: Mapping[str, str]) -> dict[str, str]:
    """Overlay explicit process values on the parsed file without empty-value fallback."""
    values = dict(file_values)
    for name in SPRING_ENVIRONMENT_ALLOWLIST | {FORBIDDEN_SINGLE_TENANT_ENVIRONMENT}:
        if name in os.environ:
            values[name] = os.environ[name]
    return values


def inspect_secret_file(
    path: Path,
    *,
    expected_uid: int | None = None,
    expected_gid: int | None = None,
) -> tuple[bool, tuple[int, int] | None, bytes | None, str | None]:
    """Return stable inode and content identities for a bounded non-symlink secret."""
    owner_uid = os.getuid() if expected_uid is None else expected_uid
    owner_gid = os.getgid() if expected_gid is None else expected_gid
    if (
        not path.is_absolute()
        or path == Path("/")
        or path != Path(os.path.normpath(path))
    ):
        return False, None, None, "must use a normalized absolute non-root path"
    ancestor_metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            parent_details = parent.lstat()
            if (
                not stat.S_ISDIR(parent_details.st_mode)
                or stat.S_ISLNK(parent_details.st_mode)
            ):
                return (
                    False,
                    None,
                    None,
                    "must not traverse symbolic-link parent directories or non-directory parents",
                )
            if (
                parent != path.parent
                and stat.S_IMODE(parent_details.st_mode) & 0o022
                and not parent_details.st_mode & stat.S_ISVTX
            ):
                return (
                    False,
                    None,
                    None,
                    "must not traverse group/other-writable non-sticky ancestors",
                )
            if (
                parent != path.parent
                and parent_details.st_uid not in {0, owner_uid}
            ):
                return (
                    False,
                    None,
                    None,
                    f"must not traverse ancestors owned outside root/runtime UID {owner_uid}",
                )
            ancestor_metadata.append((parent, stable_directory_identity(parent_details)))
        path_details = path.lstat()
    except OSError:
        return False, None, None, None
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return False, None, None, None
    if resolved.is_relative_to(ROOT.resolve()):
        return False, None, None, "must be mounted from outside the repository"
    parent_details = path.parent.lstat()
    if (
        stat.S_IMODE(parent_details.st_mode) != 0o700
        or parent_details.st_uid != owner_uid
        or parent_details.st_gid != owner_gid
    ):
        return (
            False,
            None,
            None,
            f"parent directory must be mode 0700 and owned by UID/GID {owner_uid}:{owner_gid}",
        )
    if path_details.st_nlink != 1:
        return False, None, None, "must not be hard-linked"
    if (
        not stat.S_ISREG(path_details.st_mode)
        or stat.S_ISLNK(path_details.st_mode)
        or not 32 <= path_details.st_size <= 4096
        or stat.S_IMODE(path_details.st_mode) not in {0o400, 0o600}
    ):
        return False, None, None, None
    if path_details.st_uid != owner_uid or path_details.st_gid != owner_gid:
        return (
            False,
            None,
            None,
            f"must be owned by application runtime UID/GID {owner_uid}:{owner_gid}",
        )
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
        ancestors_unchanged = all(
            not stat.S_ISLNK((current := parent.lstat()).st_mode)
            and stable_directory_identity(current) == before
            for parent, before in ancestor_metadata
        )
        if (
            stable_file_metadata(after_read_details) != stable_file_metadata(opened_details)
            or stable_file_metadata(after_read_path_details) != stable_file_metadata(opened_details)
            or len(contents) != opened_details.st_size
            or not ancestors_unchanged
        ):
            return False, None, None, "changed while it was being read"
        try:
            decoded = contents.decode("utf-8", errors="strict")
        except UnicodeError:
            return False, None, None, "must contain canonical UTF-8 bytes"
        if (
            not decoded
            or boundary_whitespace(ord(decoded[0]))
            or boundary_whitespace(ord(decoded[-1]))
        ):
            return False, None, None, "must not have leading or trailing whitespace"
        return True, identity, hashlib.sha256(contents).digest(), None
    except OSError:
        return False, None, None, "changed or became unreadable while it was being read"
    finally:
        os.close(descriptor)


def inspect_secret_group(
    entries: list[tuple[str, Path]],
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[
    dict[str, tuple[Path, tuple[int, int], bytes]],
    dict[str, str | None],
]:
    """Hold every secret inode open and prove one stable cross-file snapshot."""

    held: list[
        tuple[str, Path, int, tuple[int, ...], tuple[int, int], bytes]
    ] = []
    failures: dict[str, str | None] = {}
    results: dict[str, tuple[Path, tuple[int, int], bytes]] = {}
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        for label, path in entries:
            valid, identity, digest, failure = inspect_secret_file(
                path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            if not valid or identity is None or digest is None:
                failures[label] = failure
                continue
            descriptor = -1
            try:
                descriptor = os.open(path, flags)
                details = os.fstat(descriptor)
                path_details = path.lstat()
                chunks: list[bytes] = []
                remaining = 4097
                while remaining:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                contents = b"".join(chunks)
                if (
                    (details.st_dev, details.st_ino) != identity
                    or stable_file_metadata(path_details)
                    != stable_file_metadata(details)
                    or len(contents) != details.st_size
                    or hashlib.sha256(contents).digest() != digest
                ):
                    failures[label] = "changed while the secret group was opened"
                    os.close(descriptor)
                    continue
                held.append(
                    (
                        label,
                        path,
                        descriptor,
                        stable_file_metadata(details),
                        identity,
                        digest,
                    )
                )
            except OSError:
                failures[label] = "changed while the secret group was opened"
                if descriptor >= 0:
                    os.close(descriptor)

        for label, path, descriptor, metadata, identity, digest in held:
            try:
                os.lseek(descriptor, 0, os.SEEK_SET)
                chunks = []
                remaining = 4097
                while remaining:
                    chunk = os.read(descriptor, remaining)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                contents = b"".join(chunks)
                current = os.fstat(descriptor)
                current_path = path.lstat()
                valid, current_identity, current_digest, _ = inspect_secret_file(
                    path,
                    expected_uid=expected_uid,
                    expected_gid=expected_gid,
                )
                if (
                    stable_file_metadata(current) != metadata
                    or stable_file_metadata(current_path) != metadata
                    or len(contents) != current.st_size
                    or hashlib.sha256(contents).digest() != digest
                    or not valid
                    or current_identity != identity
                    or current_digest != digest
                ):
                    failures[label] = "changed during cross-file secret validation"
                    continue
                results[label] = (path.resolve(strict=True), identity, digest)
            except OSError:
                failures[label] = "changed during cross-file secret validation"
    finally:
        for _, _, descriptor, _, _, _ in held:
            os.close(descriptor)
    return results, failures


def inspect_owner_only_directory(
    path: Path,
    *,
    expected_uid: int | None = None,
    expected_gid: int | None = None,
) -> tuple[bool, tuple[int, int] | None, str | None]:
    """Validate the host bind root used for persistent anti-replay state."""
    owner_uid = os.getuid() if expected_uid is None else expected_uid
    owner_gid = os.getgid() if expected_gid is None else expected_gid
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        return False, None, "must use a normalized absolute non-root path"
    ancestor_metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            details = parent.lstat()
            if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
                return False, None, "must not traverse symbolic-link or non-directory parents"
            if (
                stat.S_IMODE(details.st_mode) & 0o022
                and not details.st_mode & stat.S_ISVTX
            ):
                return (
                    False,
                    None,
                    "must not traverse group/other-writable non-sticky ancestors",
                )
            if details.st_uid not in {0, owner_uid}:
                return (
                    False,
                    None,
                    f"must not traverse ancestors owned outside root/runtime UID {owner_uid}",
                )
            ancestor_metadata.append((parent, stable_directory_identity(details)))
        before = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError:
        return False, None, "must be an existing directory"
    if resolved.is_relative_to(ROOT.resolve()):
        return False, None, "must be outside the repository"
    if (
        not stat.S_ISDIR(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o700
        or before.st_uid != owner_uid
        or before.st_gid != owner_gid
        or stable_directory_identity(before) != stable_directory_identity(after)
    ):
        return (
            False,
            None,
            f"must be an owner-only 0700 non-symlink directory owned by UID/GID {owner_uid}:{owner_gid}",
        )
    try:
        if not all(
            not stat.S_ISLNK((current := parent.lstat()).st_mode)
            and stable_directory_identity(current) == expected
            for parent, expected in ancestor_metadata
        ):
            return False, None, "or a parent changed while it was being validated"
    except OSError:
        return False, None, "or a parent changed while it was being validated"
    return True, (before.st_dev, before.st_ino), None


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
    require(
        errors,
        "BODY_SHA256" in engine_filter
        and "FileNonceStore" in engine_filter
        and "nonces.claim(" in engine_filter,
        "Spring worker request authentication lacks body binding or persistent replay rejection",
    )
    require(
        errors,
        "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH" in spring_application_compose
        and "/var/lib/elmos/spring-engine-auth-replay" in spring_application_compose,
        "Spring worker persistent replay state is not bound from an explicit host directory",
    )
    require(
        errors,
        "canonicalApplicationPath(request)" in engine_filter
        and "request.getContextPath()" in engine_filter
        and "request.getServletPath()" in engine_filter,
        "Spring worker authentication is not bound to a canonical application path",
    )
    require(errors, "micrometer-registry-prometheus" in worker_pom, "Spring worker must include the Prometheus registry")
    require(
        errors,
        "\n        include: health,info\n" in worker_config,
        "Spring worker must expose only the minimal internal health and info endpoints",
    )
    require(errors, 'ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED: "false"' in compose, "production experimental routes must be hard disabled")
    require(errors, 'ELMOS_SPRING_CODING_AGENT_ENABLED: "false"' in compose, "production long-tail coding agent must be hard disabled")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in env_example, "production env template still declares a single-tenant Spring identity")
    application_environment_names = set(
        re.findall(r"^([A-Z][A-Z0-9_]*)=", env_example, re.MULTILINE)
    )
    require(
        errors,
        not application_environment_names.intersection(SPRING_ENVIRONMENT_ALLOWLIST),
        "application env template must not inject Spring launch keys into web-console",
    )


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
    expected_application_environment_commitment_digest: str | None,
    expected_effective_spring_configuration_digest: str | None,
    expected_effective_web_console_configuration_digest: str | None,
    expected_web_console_environment_names_digest: str | None,
    expected_application_mount_sources_digest: str | None,
    expected_worker_application_artifact_digest: str | None,
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
            repo_root=ROOT,
        )
    except (OSError, TypeError, ValueError) as error:
        errors.append(f"external evidence authentication failed: {error}")
        return None
    require(errors, result.get("evidence_status") == "VERIFIED_EXTERNAL_RECEIPT", "external evidence was not cryptographically verified")
    require(errors, result.get("external_evidence_intake") == "VALIDATED_NOT_CERTIFIED", "external evidence intake state drift")
    require(errors, result.get("certification") == "NOT_CERTIFIED", "external evidence must not self-certify")
    require(errors, result.get("certification_promoted") is False, "external evidence must not promote certification")
    if len(errors) != initial_error_count:
        return None
    return result


def paths_overlap(left: Path, right: Path) -> bool:
    """Return true when either canonical path contains the other."""
    return (
        left == right
        or left.is_relative_to(right)
        or right.is_relative_to(left)
    )


def validate_environment(
    errors: list[str],
    environment: Mapping[str, str],
    *,
    expected_uid: int | None = None,
    expected_gid: int | None = None,
    application_secret_path: Path | None = None,
    production: bool = False,
) -> None:
    runtime_uid = os.getuid() if expected_uid is None else expected_uid
    runtime_gid = os.getgid() if expected_gid is None else expected_gid
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
    runner_origins: list[tuple[str, str, int]] = []
    for name in SPRING_URL_ENVIRONMENT:
        origin = https_endpoint_origin(
            environment.get(name, ""), production=production
        )
        require(
            errors,
            origin is not None,
            f"{name} must use a non-local absolute https URL at the Runner origin root without credentials, query, or fragments",
        )
        if origin is not None:
            runner_origins.append(origin)
    if len(runner_origins) == len(SPRING_URL_ENVIRONMENT):
        require(
            errors,
            len(set(runner_origins)) == 1,
            "Spring verifier, transformer, and runtime URLs must use one exact Runner HTTPS origin",
        )
    workspace = Path(environment.get("ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH", ""))
    workspace_valid, workspace_identity, workspace_failure = inspect_owner_only_directory(
        workspace,
        expected_uid=runtime_uid,
        expected_gid=runtime_gid,
    )
    if not workspace_valid:
        errors.append(
            "shared Spring workspace must be an existing owner-only absolute "
            f"non-symlink directory outside the repository owned by UID/GID "
            f"{runtime_uid}:{runtime_gid}"
            + (f" ({workspace_failure})" if workspace_failure else "")
        )
    workspace_resolved = workspace.resolve(strict=True) if workspace_valid else None
    secret_paths = [
        Path(environment.get(name, "")) for name in SPRING_SECRET_PATH_ENVIRONMENT
    ]
    secret_entries = list(zip(SPRING_SECRET_PATH_ENVIRONMENT, secret_paths))
    resend_label = "web-console Resend secret"
    if application_secret_path is not None:
        secret_entries.append((resend_label, application_secret_path))
    secret_snapshots, secret_failures = inspect_secret_group(
        secret_entries,
        expected_uid=runtime_uid,
        expected_gid=runtime_gid,
    )
    for name in SPRING_SECRET_PATH_ENVIRONMENT:
        if name in secret_snapshots:
            continue
        failure = secret_failures.get(name)
        errors.append(
            f"{name} {failure}"
            if failure
            else f"{name} must be an owner-only regular 32-4096 byte file"
        )
    if application_secret_path is not None and resend_label not in secret_snapshots:
        failure = secret_failures.get(resend_label)
        errors.append(
            f"{resend_label} "
            + (failure or "must be an owner-only regular 32-4096 byte file")
        )
    hmac_snapshots = [
        secret_snapshots[name]
        for name in SPRING_SECRET_PATH_ENVIRONMENT
        if name in secret_snapshots
    ]
    resolved_secret_paths = [snapshot[0] for snapshot in hmac_snapshots]
    secret_identities = [snapshot[1] for snapshot in hmac_snapshots]
    secret_digests = [snapshot[2] for snapshot in hmac_snapshots]
    require(
        errors,
        len({os.path.normpath(str(path)) for path in secret_paths}) == len(SPRING_SECRET_PATH_ENVIRONMENT),
        "Spring HMAC secrets must use four distinct paths",
    )
    if len(secret_identities) == len(SPRING_SECRET_PATH_ENVIRONMENT):
        require(errors, len(set(secret_identities)) == len(secret_identities), "Spring HMAC secrets must use four distinct files/inodes")
        require(errors, len(set(secret_digests)) == len(secret_digests), "Spring HMAC secrets must use four distinct secret values")
    application_secret_snapshot = secret_snapshots.get(resend_label)
    application_secret_resolved = (
        application_secret_snapshot[0]
        if application_secret_snapshot is not None
        else None
    )
    if application_secret_snapshot is not None:
        require(
            errors,
            application_secret_snapshot[1] not in secret_identities,
            "web-console Resend secret must not reuse a Spring HMAC file/inode",
        )
        require(
            errors,
            application_secret_snapshot[2] not in secret_digests,
            "web-console Resend secret must not reuse a Spring HMAC value",
        )
    replay_paths: list[Path] = []
    resolved_replay_paths: list[Path] = []
    replay_identities: list[tuple[Path, tuple[int, int]]] = []
    for name in SPRING_REPLAY_PATH_ENVIRONMENT:
        replay_path = Path(environment.get(name, ""))
        replay_paths.append(replay_path)
        valid, identity, failure = inspect_owner_only_directory(
            replay_path,
            expected_uid=runtime_uid,
            expected_gid=runtime_gid,
        )
        if not valid:
            errors.append(f"{name} {failure}" if failure else f"{name} is invalid")
        else:
            replay_resolved = replay_path.resolve(strict=True)
            resolved_replay_paths.append(replay_resolved)
            if identity is not None:
                replay_identities.append((replay_path, identity))
    if workspace_resolved is not None:
        for replay_resolved in resolved_replay_paths:
            require(
                errors,
                not paths_overlap(replay_resolved, workspace_resolved),
                "Spring replay state must be isolated from the shared Spring workspace",
            )
    protected_roots: list[tuple[str, Path]] = []
    if workspace_resolved is not None:
        protected_roots.append(("shared Spring workspace", workspace_resolved))
    protected_roots.extend(
        ("Spring replay state", path) for path in resolved_replay_paths
    )
    for secret_path in resolved_secret_paths:
        for label, protected_root in protected_roots:
            require(
                errors,
                not secret_path.is_relative_to(protected_root),
                f"Spring HMAC secrets must be isolated from {label}",
            )
    if application_secret_resolved is not None:
        for label, protected_root in protected_roots:
            require(
                errors,
                not application_secret_resolved.is_relative_to(protected_root),
                f"web-console Resend secret must be isolated from {label}",
            )
    if workspace_identity is not None:
        valid, current_identity, _ = inspect_owner_only_directory(
            workspace,
            expected_uid=runtime_uid,
            expected_gid=runtime_gid,
        )
        require(
            errors,
            valid and current_identity == workspace_identity,
            "shared Spring workspace changed during environment validation",
        )
    for replay_path, replay_identity in replay_identities:
        valid, current_identity, _ = inspect_owner_only_directory(
            replay_path,
            expected_uid=runtime_uid,
            expected_gid=runtime_gid,
        )
        require(
            errors,
            valid and current_identity == replay_identity,
            "Spring replay state changed during environment validation",
        )
    final_secret_snapshots, _ = inspect_secret_group(
        secret_entries,
        expected_uid=runtime_uid,
        expected_gid=runtime_gid,
    )
    require(
        errors,
        final_secret_snapshots == secret_snapshots,
        "Spring application secret set changed during environment validation",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the bounded Spring launch profile without executing environment-file contents.",
        epilog=(
            "The Spring file accepts only allowlisted KEY=VALUE data. The actual Compose env file is "
            "parsed as inert data and bound by a secret-redacted commitment. Explicit process values take precedence for local "
            "preflight; deployment binding requires them to equal the controlled files."
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
    parser.add_argument(
        "--expected-worker-application-artifact-digest",
        help="trusted CI/build SHA-256 of the exact /app/app.jar deployed in the worker image",
    )
    parser.add_argument("--require-production-evidence", action="store_true")
    parser.add_argument("--check-environment", action="store_true")
    parser.add_argument(
        "--environment-file",
        type=Path,
        help="load an owner-only Spring environment file from outside the repository; implies --check-environment",
    )
    parser.add_argument(
        "--compose-environment-file",
        type=Path,
        help=(
            "load and bind a secret-redacted commitment for the owner-only ELMOS_ENV_FILE used by the production "
            "Compose deployment; requires --environment-file"
        ),
    )
    args = parser.parse_args()
    errors: list[str] = []
    if args.expected_revision is not None:
        require(
            errors,
            GIT_REVISION.fullmatch(args.expected_revision) is not None,
            "--expected-revision must be 40 lowercase hexadecimal characters",
        )
    if args.expected_worker_application_artifact_digest is not None:
        require(
            errors,
            SHA256_DIGEST.fullmatch(
                args.expected_worker_application_artifact_digest
            )
            is not None,
            "--expected-worker-application-artifact-digest must be sha256 followed by 64 lowercase hexadecimal characters",
        )
    profile = load(PROFILE)
    validate_contract(errors, profile)
    validate_code(errors)
    file_environment = parse_environment_file(errors, args.environment_file) if args.environment_file else {}
    if args.environment_file is not None:
        for name in sorted(SPRING_ENVIRONMENT_ALLOWLIST - file_environment.keys()):
            errors.append(f"SPRING_ENV_FILE is missing required key {name}")
    compose_environment: dict[str, str] = {}
    application_environment_commitment: str | None = None
    if args.compose_environment_file:
        compose_environment = parse_compose_environment_file(
            errors, args.compose_environment_file
        )
        if args.environment_file is None:
            errors.append("--compose-environment-file requires --environment-file")
        else:
            validate_compose_environment_binding(
                errors,
                path=args.compose_environment_file,
                compose_environment=compose_environment,
                spring_environment=file_environment,
            )
    check_environment = (
        args.check_environment
        or args.environment_file is not None
        or args.compose_environment_file is not None
    )
    effective = effective_environment(file_environment)
    application_secret_path = (
        Path(compose_environment.get("ELMOS_SECRET_ROOT", "/srv/elmos/secrets"))
        / "resend-api-key"
        if args.compose_environment_file is not None
        else None
    )
    configuration_digest: str | None = None
    expected_effective_spring_configuration_digest: str | None = None
    expected_effective_web_console_configuration_digest: str | None = None
    expected_web_console_environment_names_digest: str | None = None
    expected_application_mount_sources_digest: str | None = None
    if check_environment:
        production_identity = (
            args.require_production_evidence or args.external_evidence is not None
        )
        runtime_uid = APPLICATION_RUNTIME_UID if production_identity else os.getuid()
        runtime_gid = APPLICATION_RUNTIME_GID if production_identity else os.getgid()
        validate_environment(
            errors,
            effective,
            expected_uid=runtime_uid,
            expected_gid=runtime_gid,
            application_secret_path=application_secret_path,
            production=production_identity,
        )
        try:
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from scripts.batch30.spring_launch_evidence import (
                application_environment_commitment_digest as derive_application_environment_commitment,
                application_mount_sources_digest,
                expected_web_console_environment,
                expected_web_console_environment_names,
                expected_spring_worker_configuration_digest,
                spring_environment_configuration_digest,
                web_console_configuration_digest,
                web_console_environment_names_digest,
            )

            spring_configuration_digest = spring_environment_configuration_digest(effective)
            if args.compose_environment_file is not None:
                application_environment_commitment = (
                    derive_application_environment_commitment(compose_environment)
                )
            configuration_digest = (
                deployment_configuration_digest(
                    spring_configuration_digest, application_environment_commitment
                )
                if application_environment_commitment is not None
                else spring_configuration_digest
            )
            expected_effective_spring_configuration_digest = (
                expected_spring_worker_configuration_digest(effective)
            )
            if application_environment_commitment is not None:
                expected_web_environment = expected_web_console_environment(
                    compose_environment
                )
                expected_effective_web_console_configuration_digest = (
                    web_console_configuration_digest(expected_web_environment)
                )
                expected_web_console_environment_names_digest = (
                    web_console_environment_names_digest(
                        expected_web_console_environment_names(compose_environment)
                    )
                )
                if application_secret_path is None:
                    raise ValueError(
                        "application mount binding requires the Compose environment file"
                    )
                application_mount_sources = {
                    "worker_workspace": effective.get(
                        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH", ""
                    ),
                    "worker_verifier_hmac": effective.get(
                        "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH", ""
                    ),
                    "worker_transformer_hmac": effective.get(
                        "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH", ""
                    ),
                    "worker_runtime_hmac": effective.get(
                        "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH", ""
                    ),
                    "application_engine_hmac": effective.get(
                        "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH", ""
                    ),
                    "worker_engine_replay": effective.get(
                        "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH", ""
                    ),
                    "web_resend_secret": str(application_secret_path),
                }
                first_mount_sources_digest = application_mount_sources_digest(
                    application_mount_sources,
                    expected_uid=runtime_uid,
                    expected_gid=runtime_gid,
                )
                validate_environment(
                    errors,
                    effective,
                    expected_uid=runtime_uid,
                    expected_gid=runtime_gid,
                    application_secret_path=application_secret_path,
                    production=production_identity,
                )
                expected_application_mount_sources_digest = (
                    application_mount_sources_digest(
                        application_mount_sources,
                        expected_uid=runtime_uid,
                        expected_gid=runtime_gid,
                    )
                )
                require(
                    errors,
                    expected_application_mount_sources_digest
                    == first_mount_sources_digest,
                    "application mount source objects changed during launch binding",
                )
        except (OSError, TypeError, ValueError) as error:
            errors.append(f"Spring environment configuration digest failed: {error}")

    if args.require_production_evidence:
        required_production_arguments = {
            "--environment-file": args.environment_file,
            "--compose-environment-file": args.compose_environment_file,
            "--expected-revision": args.expected_revision,
            "--expected-trust-store-digest": args.expected_trust_store_digest,
            "--expected-environment-id": args.expected_environment_id,
            "--expected-deployment-id": args.expected_deployment_id,
            "--expected-provider": args.expected_provider,
            "--expected-region": args.expected_region,
            "--expected-environment-class": args.expected_environment_class,
            "--expected-worker-application-artifact-digest": (
                args.expected_worker_application_artifact_digest
            ),
        }
        for option, value in required_production_arguments.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"production evidence requires {option}")

    if args.external_evidence and not args.require_production_evidence:
        required_intake_arguments = {
            "--environment-file": args.environment_file,
            "--compose-environment-file": args.compose_environment_file,
            "--expected-revision": args.expected_revision,
            "--expected-trust-store-digest": args.expected_trust_store_digest,
            "--expected-environment-id": args.expected_environment_id,
            "--expected-deployment-id": args.expected_deployment_id,
            "--expected-provider": args.expected_provider,
            "--expected-region": args.expected_region,
            "--expected-environment-class": args.expected_environment_class,
            "--expected-worker-application-artifact-digest": (
                args.expected_worker_application_artifact_digest
            ),
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
                expected_application_environment_commitment_digest=(
                    application_environment_commitment
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
                    args.expected_worker_application_artifact_digest
                ),
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
        if application_environment_commitment is not None:
            print("COMPOSE_ENVIRONMENT_BINDING=ELMOS_ENV_FILE_VERIFIED")
            print(
                "APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST="
                f"{application_environment_commitment}"
            )
        print(f"SPRING_CONFIGURATION_DIGEST={configuration_digest}")
        print(
            "EXPECTED_SPRING_WORKER_CONFIGURATION_DIGEST="
            f"{expected_effective_spring_configuration_digest}"
        )
        if expected_effective_web_console_configuration_digest is not None:
            print(
                "EXPECTED_WEB_CONSOLE_CONFIGURATION_DIGEST="
                f"{expected_effective_web_console_configuration_digest}"
            )
        if expected_web_console_environment_names_digest is not None:
            print(
                "EXPECTED_WEB_CONSOLE_ENVIRONMENT_NAMES_DIGEST="
                f"{expected_web_console_environment_names_digest}"
            )
        if expected_application_mount_sources_digest is not None:
            print(
                "EXPECTED_APPLICATION_MOUNT_SOURCES_DIGEST="
                f"{expected_application_mount_sources_digest}"
            )
    print("EXTERNAL_EVIDENCE_INTAKE=" + ("VALIDATED_NOT_CERTIFIED" if args.external_evidence else "NOT_RUN"))
    print("CERTIFICATION=NOT_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
