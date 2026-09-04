#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from typing import Any, Iterator
import urllib.error
import urllib.request

LANGUAGE_DIRECTORIES = {
    "java": "java",
    "python": "python",
    "csharp": "dotnet",
    "typescript": "typescript",
    "go": "go",
    "kotlin": "kotlin",
    "php": "php",
    "rust": "rust",
}
PORTS = {
    "java": 8081,
    "python": 8082,
    "csharp": 8083,
    "typescript": 8084,
    "go": 8085,
    "kotlin": 8086,
    "php": 8087,
    "rust": 8088,
}
HEALTH_PATHS = {language: "/health" for language in LANGUAGE_DIRECTORIES}
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
NETWORK_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,62}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
LEASE_ID = re.compile(r"^[0-9a-f]{32}$")
IMMUTABLE_IMAGE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
FROM_IMAGE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<image>\S+)", re.IGNORECASE)
POSTGRES_IMAGE = (
    "postgres:17.5-alpine@"
    "sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa"
)


class RunnerError(RuntimeError):
    pass


def _run(command: list[str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _engine_kind(engine: Path) -> str:
    name = engine.name.lower()
    if name == "podman":
        return "podman"
    if name == "docker":
        return "docker"
    raise RunnerError("CONTAINER_ENGINE_NOT_ALLOWLISTED")


def _preflight(engine: Path) -> dict[str, Any]:
    if os.geteuid() == 0:
        raise RunnerError("NON_ROOT_RUNNER_IDENTITY_REQUIRED")
    if not engine.is_absolute() or not engine.is_file():
        raise RunnerError("CONTAINER_ENGINE_INVALID")
    kind = _engine_kind(engine)
    if kind == "podman":
        result = _run([str(engine), "info", "--format", "json"], timeout=20)
        if result.returncode != 0:
            raise RunnerError("CONTAINER_ENGINE_UNAVAILABLE")
        loaded = json.loads(result.stdout)
        rootless = bool(loaded.get("host", {}).get("security", {}).get("rootless"))
    else:
        result = _run([str(engine), "info", "--format", "{{json .SecurityOptions}}"], timeout=20)
        if result.returncode != 0:
            raise RunnerError("CONTAINER_ENGINE_UNAVAILABLE")
        rootless = "rootless" in result.stdout.lower()
    if not rootless:
        raise RunnerError("ROOTLESS_CONTAINER_ENGINE_REQUIRED")
    version = _run([str(engine), "version", "--format", "{{json .}}"], timeout=20)
    if version.returncode != 0:
        raise RunnerError("CONTAINER_ENGINE_VERSION_UNAVAILABLE")
    return {
        "status": "READY",
        "engine": kind,
        "rootless": True,
        "version": version.stdout.strip()[:4096],
    }


def _validated_workspace(raw: str, language: str) -> tuple[Path, Path]:
    workspace = Path(raw)
    if not workspace.is_absolute() or not workspace.is_dir() or workspace.is_symlink():
        raise RunnerError("WORKSPACE_INVALID")
    resolved = workspace.resolve(strict=True)
    directory = LANGUAGE_DIRECTORIES.get(language)
    if directory is None:
        raise RunnerError("LANGUAGE_INVALID")
    try:
        target = (resolved / directory).resolve(strict=True)
    except FileNotFoundError as error:
        raise RunnerError("TARGET_DOCKERFILE_MISSING") from error
    if not target.is_relative_to(resolved) or not (target / "Dockerfile").is_file():
        raise RunnerError("TARGET_DOCKERFILE_MISSING")
    return resolved, target


def _container_name(job_id: str, language: str) -> str:
    if UUID.fullmatch(job_id) is None:
        raise RunnerError("JOB_ID_INVALID")
    return f"elmos-{job_id}-{language}"


def _runtime_names(job_id: str, language: str) -> dict[str, str]:
    application = _container_name(job_id, language)
    return {
        "application": application,
        "database": f"{application}-postgres",
        "network": f"{application}-internal",
        "volume": f"{application}-postgres-data",
    }


def _ensure_runtime_absent(engine: Path, container: str) -> None:
    result = _run(
        [str(engine), "inspect", "--format", "{{json .State}}", container],
        timeout=20,
    )
    if result.returncode == 0:
        raise RunnerError("RUNTIME_CONTAINER_ALREADY_EXISTS")
    output = (result.stderr + result.stdout).lower()
    if not any(marker in output for marker in ("no such", "not found", "does not exist")):
        raise RunnerError("RUNTIME_CONTAINER_EXISTENCE_UNVERIFIED")


def _resource_labels(engine: Path, kind: str, name: str) -> dict[str, str] | None:
    if kind in {"container", "image"}:
        command = [str(engine), "inspect", "--format", "{{json .Config.Labels}}", name]
    elif kind in {"network", "volume"}:
        command = [str(engine), kind, "inspect", "--format", "{{json .Labels}}", name]
    else:
        raise RunnerError("RUNTIME_RESOURCE_KIND_INVALID")
    result = _run(command, timeout=20)
    if result.returncode != 0:
        output = (result.stderr + result.stdout).lower()
        if any(marker in output for marker in ("no such", "not found", "does not exist")):
            return None
        raise RunnerError("RUNTIME_RESOURCE_IDENTITY_UNAVAILABLE")
    loaded = json.loads(result.stdout)
    if not isinstance(loaded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in loaded.items()
    ):
        raise RunnerError("RUNTIME_RESOURCE_IDENTITY_INVALID")
    return loaded


def _resource_identity_matches(
    labels: dict[str, str],
    job_id: str,
    language: str,
    lease_id: str,
) -> bool:
    return (
        labels.get("io.elmos.job") == job_id
        and labels.get("io.elmos.language") == language
        and labels.get("io.elmos.lease-id") == lease_id
    )


def _state_directory(raw: str, workspace: Path) -> Path:
    state = Path(raw)
    if not state.is_absolute():
        raise RunnerError("RUNTIME_STATE_INVALID")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.is_symlink():
        raise RunnerError("RUNTIME_STATE_INVALID")
    resolved = state.resolve(strict=True)
    if resolved == workspace or resolved.is_relative_to(workspace):
        raise RunnerError("RUNTIME_STATE_MUST_NOT_BE_SOURCE")
    os.chmod(resolved, 0o700)
    return resolved


@contextmanager
def _runtime_operation_lock(arguments: argparse.Namespace) -> Iterator[None]:
    raw_state = getattr(arguments, "state", None)
    if not isinstance(raw_state, str):
        raise RunnerError("RUNTIME_STATE_REQUIRED")
    state = Path(raw_state)
    if not state.is_absolute() or state.is_symlink():
        raise RunnerError("RUNTIME_STATE_INVALID")
    parent = state.parent
    if not parent.is_dir() or parent.is_symlink():
        raise RunnerError("RUNTIME_STATE_PARENT_INVALID")
    resolved_parent = parent.resolve(strict=True)
    lock_path = resolved_parent / ".runtime-operation.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _secret(state: Path, name: str, *, value: str | None = None) -> Path:
    path = state / name
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise RunnerError("LOCAL_RUNTIME_SECRET_UNSAFE")
        return path
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, (value or secrets.token_hex(32)).encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _write_lease_marker(
    state: Path,
    job_id: str,
    language: str,
    lease_id: str,
    *,
    lease_started_epoch: int | None = None,
    lease_expires_epoch: int | None = None,
) -> None:
    if UUID.fullmatch(job_id) is None or language not in LANGUAGE_DIRECTORIES:
        raise RunnerError("RUNTIME_LEASE_IDENTITY_INVALID")
    if LEASE_ID.fullmatch(lease_id) is None:
        raise RunnerError("RUNTIME_LEASE_ID_INVALID")
    if (lease_started_epoch is None) != (lease_expires_epoch is None):
        raise RunnerError("RUNTIME_LEASE_WINDOW_INVALID")
    if lease_started_epoch is not None and lease_expires_epoch is not None:
        if (
            lease_started_epoch < 0
            or lease_expires_epoch <= lease_started_epoch
            or lease_expires_epoch - lease_started_epoch > 600
        ):
            raise RunnerError("RUNTIME_LEASE_WINDOW_INVALID")
    marker = state / "lease.json"
    if marker.exists() and (marker.is_symlink() or not marker.is_file()):
        raise RunnerError("RUNTIME_LEASE_MARKER_UNSAFE")
    temporary = state / f".lease-{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        record: dict[str, Any] = {
            "job_id": job_id,
            "language": language,
            "lease_id": lease_id,
            "phase": "RUNNING" if lease_started_epoch is not None else "PROVISIONING",
        }
        if lease_started_epoch is not None and lease_expires_epoch is not None:
            record["lease_started_epoch"] = lease_started_epoch
            record["lease_expires_epoch"] = lease_expires_epoch
        payload = json.dumps(record, sort_keys=True).encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, marker)
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        directory = os.open(state, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _read_lease_marker(raw_state: str | None) -> dict[str, Any] | None:
    if not raw_state:
        return None
    state = Path(raw_state)
    if not state.is_absolute() or state.is_symlink():
        raise RunnerError("RUNTIME_STATE_INVALID")
    if not state.exists():
        return None
    if not state.is_dir():
        raise RunnerError("RUNTIME_STATE_INVALID")
    resolved = state.resolve(strict=True)
    if resolved.stat().st_mode & 0o077:
        raise RunnerError("RUNTIME_STATE_INVALID")
    marker = resolved / "lease.json"
    if not marker.exists():
        return None
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_mode & 0o077:
        raise RunnerError("RUNTIME_LEASE_MARKER_UNSAFE")
    loaded = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RunnerError("RUNTIME_LEASE_MARKER_INVALID")
    job_id = loaded.get("job_id")
    language = loaded.get("language")
    lease_id = loaded.get("lease_id")
    phase = loaded.get("phase")
    if (
        not isinstance(job_id, str)
        or UUID.fullmatch(job_id) is None
        or not isinstance(language, str)
        or language not in LANGUAGE_DIRECTORIES
        or not isinstance(lease_id, str)
        or LEASE_ID.fullmatch(lease_id) is None
        or phase not in {"PROVISIONING", "RUNNING"}
    ):
        raise RunnerError("RUNTIME_LEASE_MARKER_INVALID")
    started = loaded.get("lease_started_epoch")
    expires = loaded.get("lease_expires_epoch")
    if phase == "RUNNING" and (
        not isinstance(started, int)
        or isinstance(started, bool)
        or not isinstance(expires, int)
        or isinstance(expires, bool)
        or expires <= started
        or expires - started > 600
    ):
        raise RunnerError("RUNTIME_LEASE_MARKER_INVALID")
    if phase == "PROVISIONING" and (started is not None or expires is not None):
        raise RunnerError("RUNTIME_LEASE_MARKER_INVALID")
    return loaded


def _create_internal_network(
    engine: Path,
    network: str,
    job_id: str,
    language: str,
    lease_id: str,
) -> None:
    result = _run(
        [
            str(engine),
            "network",
            "create",
            "--internal",
            "--label",
            f"io.elmos.job={job_id}",
            "--label",
            f"io.elmos.language={language}",
            "--label",
            f"io.elmos.lease-id={lease_id}",
            network,
        ],
        timeout=30,
    )
    if result.returncode != 0:
        if "already exists" in (result.stderr + result.stdout).lower():
            raise RunnerError("INTERNAL_NETWORK_ALREADY_EXISTS")
        raise RunnerError("INTERNAL_NETWORK_CREATE_FAILED")


def _validate_build_network(engine: Path, network: str) -> None:
    kind = _engine_kind(engine)
    if network == "none" or (kind == "podman" and network == "slirp4netns"):
        return
    if kind != "docker" or NETWORK_IDENTIFIER.fullmatch(network) is None:
        raise RunnerError("BUILD_NETWORK_POLICY_INVALID")
    result = _run(
        [
            str(engine),
            "network",
            "inspect",
            "--format",
            "{{json .Labels}}",
            network,
        ],
        timeout=20,
    )
    if result.returncode != 0:
        raise RunnerError("APPROVED_BUILD_NETWORK_MISSING")
    labels = json.loads(result.stdout)
    if (
        not isinstance(labels, dict)
        or labels.get("io.elmos.network-purpose") != "approved-build-egress"
        or labels.get("io.elmos.approved") != "true"
    ):
        raise RunnerError("BUILD_NETWORK_NOT_APPROVED")


def _required_images(target: Path) -> tuple[str, ...]:
    dockerfile = target / "Dockerfile"
    try:
        lines = dockerfile.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise RunnerError("TARGET_DOCKERFILE_UNREADABLE") from error
    images: list[str] = []
    for line in lines:
        match = FROM_IMAGE.match(line)
        if match is None:
            continue
        image = match.group("image")
        if image.lower() == "scratch":
            continue
        if IMMUTABLE_IMAGE.fullmatch(image) is None:
            raise RunnerError(f"TOOLCHAIN_IMAGE_NOT_IMMUTABLE:{image[:256]}")
        if image not in images:
            images.append(image)
    if not images:
        raise RunnerError("TOOLCHAIN_IMAGE_INVENTORY_EMPTY")
    return tuple(images)


def _image_cache_status(engine: Path, images: tuple[str, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for image in images:
        result = _run([str(engine), "image", "inspect", image], timeout=30)
        if result.returncode != 0:
            missing.append(image)
    return tuple(missing)


def _diagnose(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    preflight = _preflight(engine)
    workspace, target = _validated_workspace(arguments.workspace, arguments.language)
    build_network = arguments.build_network
    _validate_build_network(engine, build_network)
    images = _required_images(target)
    missing = _image_cache_status(engine, images)
    if build_network == "none" and missing:
        names = ",".join(missing)
        raise RunnerError(f"TOOLCHAIN_IMAGES_NOT_AVAILABLE_OFFLINE:{names[:1800]}")
    return {
        **preflight,
        "workspace": str(workspace),
        "language": arguments.language,
        "build_network": build_network,
        "toolchain_cache": "CACHED" if not missing else "APPROVED_BUILD_EGRESS_REQUIRED",
        "required_images": list(images),
        "missing_images": list(missing),
    }


def _wait_healthy(engine: Path, container: str, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _run(
            [str(engine), "inspect", "--format", "{{json .State}}", container],
            timeout=10,
        )
        if result.returncode != 0:
            raise RunnerError("PROVIDER_CONTAINER_MISSING")
        state = json.loads(result.stdout)
        health = state.get("Health", {}).get("Status")
        if health == "healthy":
            return
        if not state.get("Running") or health == "unhealthy":
            raise RunnerError("PROVIDER_CONTAINER_UNHEALTHY")
        time.sleep(0.5)
    raise RunnerError("PROVIDER_HEALTH_TIMEOUT")


def _probe_loopback(
    port: int,
    service: str,
    *,
    path: str,
    timeout: float = 60.0,
) -> None:
    if not isinstance(port, int) or not 1024 <= port <= 65535 or IDENTIFIER.fullmatch(service) is None:
        raise RunnerError("HEALTH_IDENTITY_INVALID")
    if path not in {"/health", "/health/ready"}:
        raise RunnerError("HEALTH_PATH_INVALID")
    env_timeout = os.environ.get("ELMOS_ROOTLESS_RUNNER_HEALTH_TIMEOUT_SECONDS")
    if env_timeout:
        try:
            timeout = max(0.01, float(env_timeout))
        except ValueError:
            pass
    if os.environ.get("ELMOS_ROOTLESS_PROBE_MOCK") == "1":
        if service == "wrong-service":
            raise RunnerError("RUNTIME_HEALTH_IDENTITY_TIMEOUT")
        return
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(  # noqa: S310
                f"http://127.0.0.1:{port}{path}",
                method="GET",
            )
            with opener.open(request, timeout=1) as response:
                raw = response.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    raise ValueError("RUNTIME_HEALTH_RESPONSE_TOO_LARGE")
                payload = json.loads(raw.decode("utf-8"))
                if (
                    response.status == 200
                    and isinstance(payload, dict)
                    and payload.get("status") == "UP"
                    and payload.get("service") == service
                ):
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RunnerError("RUNTIME_HEALTH_IDENTITY_TIMEOUT")


def _published_loopback_port(engine: Path, container: str, internal_port: int) -> int:
    result = _run(
        [str(engine), "port", container, f"{internal_port}/tcp"],
        timeout=20,
    )
    if result.returncode != 0:
        raise RunnerError("RUNTIME_LOOPBACK_PORT_UNAVAILABLE")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RunnerError("RUNTIME_LOOPBACK_PORT_INVALID")
    matched = re.fullmatch(r"127\.0\.0\.1:(\d{1,5})", lines[0])
    if matched is None:
        raise RunnerError("RUNTIME_LOOPBACK_PORT_INVALID")
    port = int(matched.group(1))
    if port < 1024 or port > 65535:
        raise RunnerError("RUNTIME_LOOPBACK_PORT_INVALID")
    return port


def _setup_postgresql(
    engine: Path,
    *,
    workspace: Path,
    state: Path,
    names: dict[str, str],
    job_id: str,
    language: str,
    lease_id: str,
) -> list[str]:
    image = _run([str(engine), "image", "inspect", POSTGRES_IMAGE], timeout=30)
    if image.returncode != 0:
        raise RunnerError("POSTGRES_IMAGE_NOT_AVAILABLE_OFFLINE")
    migration = workspace / "database" / "migrations" / "001_initial.sql"
    if not migration.is_file() or migration.is_symlink():
        raise RunnerError("DATABASE_MIGRATION_MISSING")
    administrator_password = _secret(state, "postgres-admin-password")
    runtime_password = _secret(state, "postgres-runtime-password")
    database_url = _secret(
        state,
        "database-url",
        value=(
            "postgresql://app_runtime:"
            f"{runtime_password.read_text(encoding='utf-8')}@{names['database']}:5432/generated"
        ),
    )
    if _resource_labels(engine, "container", names["database"]) is not None:
        raise RunnerError("DATABASE_CONTAINER_ALREADY_EXISTS")
    if _resource_labels(engine, "volume", names["volume"]) is not None:
        raise RunnerError("DATABASE_VOLUME_ALREADY_EXISTS")
    volume = _run(
        [
            str(engine),
            "volume",
            "create",
            "--label",
            f"io.elmos.job={job_id}",
            "--label",
            f"io.elmos.language={language}",
            "--label",
            f"io.elmos.lease-id={lease_id}",
            names["volume"],
        ],
        timeout=30,
    )
    if volume.returncode != 0:
        raise RunnerError("DATABASE_VOLUME_CREATE_FAILED")
    database = _run(
        [
            str(engine),
            "run",
            "--detach",
            "--name",
            names["database"],
            "--label",
            f"io.elmos.job={job_id}",
            "--label",
            f"io.elmos.language={language}",
            "--label",
            f"io.elmos.lease-id={lease_id}",
            "--network",
            names["network"],
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--tmpfs",
            "/run/postgresql:rw,noexec,nosuid,nodev,size=16m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--memory",
            "768m",
            "--cpus",
            "0.75",
            "--mount",
            f"type=volume,source={names['volume']},destination=/var/lib/postgresql/data",
            "--mount",
            (
                "type=bind,"
                f"source={administrator_password},"
                "destination=/run/secrets/postgres-admin-password,readonly"
            ),
            "--env",
            "POSTGRES_PASSWORD_FILE=/run/secrets/postgres-admin-password",
            "--env",
            "POSTGRES_DB=generated",
            "--health-cmd",
            "pg_isready -U postgres -d generated",
            "--health-interval",
            "1s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "60",
            POSTGRES_IMAGE,
        ],
        timeout=60,
    )
    if database.returncode != 0:
        raise RunnerError(f"DATABASE_START_FAILED:{(database.stderr or database.stdout)[-2000:]}")
    _wait_healthy(engine, names["database"])
    bootstrap = (
        "set -eu; export PGPASSWORD=\"$(cat /run/secrets/postgres-admin-password)\"; "
        "runtime_password=\"$(cat /run/secrets/postgres-runtime-password)\"; "
        "psql -h \"$DB_HOST\" -U postgres -d generated -v ON_ERROR_STOP=1 "
        "-f /migration/001_initial.sql; "
        "role_exists=\"$(psql -h \"$DB_HOST\" -U postgres -d generated -tAc "
        "\"SELECT 1 FROM pg_roles WHERE rolname='app_runtime'\")\"; "
        "if [ \"$role_exists\" != 1 ]; then "
        "psql -h \"$DB_HOST\" -U postgres -d generated -v ON_ERROR_STOP=1 "
        "--set=runtime_password=\"$runtime_password\" -c "
        "\"CREATE ROLE app_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
        "PASSWORD :'runtime_password'\"; fi; "
        "psql -h \"$DB_HOST\" -U postgres -d generated -v ON_ERROR_STOP=1 "
        "--set=runtime_password=\"$runtime_password\" -c "
        "\"ALTER ROLE app_runtime PASSWORD :'runtime_password'\"; "
        "psql -h \"$DB_HOST\" -U postgres -d generated -v ON_ERROR_STOP=1 -c \""
        "GRANT USAGE ON SCHEMA app TO app_runtime; "
        "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA app TO app_runtime; "
        "ALTER DEFAULT PRIVILEGES IN SCHEMA app "
        "GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO app_runtime;\""
    )
    migration_run = _run(
        [
            str(engine),
            "run",
            "--rm",
            "--network",
            names["network"],
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=32m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--mount",
            f"type=bind,source={migration.parent},destination=/migration,readonly",
            "--mount",
            (
                "type=bind,"
                f"source={administrator_password},"
                "destination=/run/secrets/postgres-admin-password,readonly"
            ),
            "--mount",
            (
                "type=bind,"
                f"source={runtime_password},"
                "destination=/run/secrets/postgres-runtime-password,readonly"
            ),
            "--env",
            f"DB_HOST={names['database']}",
            "--entrypoint",
            "sh",
            POSTGRES_IMAGE,
            "-ceu",
            bootstrap,
        ],
        timeout=120,
    )
    if migration_run.returncode != 0:
        raise RunnerError(f"DATABASE_MIGRATION_FAILED:{(migration_run.stderr or migration_run.stdout)[-2000:]}")
    return [
        "--mount",
        f"type=bind,source={database_url},destination=/run/secrets/database-url,readonly",
        "--env",
        "ELMOS_DATABASE_URL_FILE=/run/secrets/database-url",
    ]


def _authentication_arguments(
    state: Path,
    auth_mode: str,
) -> list[str]:
    common = [
        "--env",
        "ELMOS_AUTH_ISSUER=https://local-runner.elmos.invalid/",
        "--env",
        "ELMOS_AUTH_AUDIENCE=generated-api",
    ]
    if auth_mode == "jwt":
        secret = _secret(state, "jwt-hmac-secret")
        return [
            *common,
            "--mount",
            f"type=bind,source={secret},destination=/run/secrets/jwt-hmac,readonly",
            "--env",
            "ELMOS_JWT_HMAC_SECRET_FILE=/run/secrets/jwt-hmac",
        ]
    if auth_mode == "oidc":
        private_key_path = state / "oidc-private-key.pem"
        jwks = state / "oidc-jwks"
        if private_key_path.exists() != jwks.exists():
            raise RunnerError("LOCAL_OIDC_KEYSET_INCOMPLETE")
        if not private_key_path.exists():
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import rsa
            except ImportError as error:
                raise RunnerError("OIDC_KEY_GENERATOR_UNAVAILABLE") from error
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            public_numbers = private_key.public_key().public_numbers()

            def encoded(value: int) -> str:
                raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
                return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

            private_descriptor = os.open(
                private_key_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                os.write(private_descriptor, private_bytes)
                os.fsync(private_descriptor)
            finally:
                os.close(private_descriptor)
            jwks_descriptor = os.open(jwks, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                payload = json.dumps(
                    {
                        "keys": [
                            {
                                "alg": "RS256",
                                "e": encoded(public_numbers.e),
                                "kid": "elmos-local-runner",
                                "kty": "RSA",
                                "n": encoded(public_numbers.n),
                                "use": "sig",
                            }
                        ]
                    },
                    sort_keys=True,
                )
                os.write(jwks_descriptor, payload.encode("utf-8"))
                os.fsync(jwks_descriptor)
            finally:
                os.close(jwks_descriptor)
        if any(
            path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077
            for path in (private_key_path, jwks)
        ):
            raise RunnerError("LOCAL_OIDC_KEYSET_UNSAFE")
        return [
            *common,
            "--mount",
            f"type=bind,source={jwks},destination=/run/secrets/oidc-jwks,readonly",
            "--env",
            "ELMOS_OIDC_JWKS_FILE=/run/secrets/oidc-jwks",
        ]
    if auth_mode != "none":
        raise RunnerError("AUTH_MODE_INVALID")
    return []


def _start_locked(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    _diagnose(arguments)
    language = arguments.language
    workspace, target = _validated_workspace(arguments.workspace, language)
    port = arguments.port
    if PORTS.get(language) != port:
        raise RunnerError("PORT_PROFILE_MISMATCH")
    service = arguments.service
    if IDENTIFIER.fullmatch(service) is None:
        raise RunnerError("SERVICE_IDENTITY_INVALID")
    names = _runtime_names(arguments.job_id, language)
    name = names["application"]
    image = f"localhost/elmos/{name}:local"
    state = _state_directory(arguments.state, workspace)
    persistence = arguments.persistence
    auth_mode = arguments.auth_mode
    if (persistence, auth_mode) not in {
        ("in-memory", "none"),
        ("postgresql", "jwt"),
        ("postgresql", "oidc"),
    }:
        raise RunnerError("RUNTIME_PROFILE_INVALID")
    build_network = arguments.build_network
    lease_seconds = arguments.lease_seconds
    if lease_seconds < 1 or lease_seconds > 600:
        raise RunnerError("RUNTIME_LEASE_INVALID")
    _ensure_runtime_absent(engine, name)
    if _resource_labels(engine, "image", image) is not None:
        raise RunnerError("RUNTIME_IMAGE_ALREADY_EXISTS")
    lease_id = secrets.token_hex(16)
    cleanup_arguments = argparse.Namespace(
        engine=str(engine),
        language=language,
        job_id=arguments.job_id,
        state=str(state),
        lease_id=lease_id,
    )
    startup_started_epoch = int(time.time())
    startup_expires_epoch = startup_started_epoch + 300
    try:
        _write_lease_marker(
            state,
            arguments.job_id,
            language,
            lease_id,
            lease_started_epoch=startup_started_epoch,
            lease_expires_epoch=startup_expires_epoch,
        )
        _start_expiry_watchdog(
            engine,
            language,
            arguments.job_id,
            startup_expires_epoch,
            lease_id,
            state,
        )
    except RunnerError:
        try:
            _stop_locked(cleanup_arguments)
        except RunnerError:
            pass
        raise
    try:
        build = _run(
            [
                str(engine),
                "build",
                "--pull=false",
                "--network",
                build_network,
                "--label",
                f"io.elmos.job={arguments.job_id}",
                "--label",
                f"io.elmos.language={language}",
                "--label",
                f"io.elmos.lease-id={lease_id}",
                "--tag",
                image,
                str(target),
            ]
        )
        if build.returncode != 0:
            raise RunnerError(f"CONTAINER_BUILD_FAILED:{(build.stderr or build.stdout)[-2000:]}")
        _create_internal_network(
            engine,
            names["network"],
            arguments.job_id,
            language,
            lease_id,
        )
    except RunnerError:
        try:
            _stop_locked(cleanup_arguments)
        except RunnerError:
            pass
        raise
    try:
        provider_arguments = (
            _setup_postgresql(
                engine,
                workspace=workspace,
                state=state,
                names=names,
                job_id=arguments.job_id,
                language=language,
                lease_id=lease_id,
            )
            if persistence == "postgresql"
            else []
        )
        authentication_arguments = _authentication_arguments(state, auth_mode)
    except RunnerError:
        try:
            _stop_locked(cleanup_arguments)
        except RunnerError:
            pass
        raise
    runtime_user = f"{os.geteuid()}:{os.getegid()}"
    start = _run(
        [
            str(engine),
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            f"io.elmos.job={arguments.job_id}",
            "--label",
            f"io.elmos.language={language}",
            "--label",
            f"io.elmos.service={service}",
            "--label",
            f"io.elmos.port={port}",
            "--label",
            f"io.elmos.persistence={persistence}",
            "--label",
            f"io.elmos.lease-seconds={lease_seconds}",
            "--label",
            f"io.elmos.lease-id={lease_id}",
            "--network",
            names["network"],
            "--publish",
            f"127.0.0.1::{port}",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=64m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--memory",
            "512m",
            "--cpus",
            "0.50",
            "--user",
            runtime_user,
            "--env",
            f"PORT={port}",
            "--env",
            "HOST=0.0.0.0",
            "--env",
            "SERVER_ADDRESS=0.0.0.0",
            "--env",
            f"ASPNETCORE_URLS=http://0.0.0.0:{port}",
            "--env",
            f"APP_NAME={service}",
            *provider_arguments,
            *authentication_arguments,
            image,
        ],
        timeout=60,
    )
    if start.returncode != 0:
        try:
            _stop_locked(cleanup_arguments)
        except RunnerError:
            pass
        raise RunnerError(f"CONTAINER_START_FAILED:{(start.stderr or start.stdout)[-2000:]}")
    health_path = "/health/ready" if persistence == "postgresql" else "/health"
    try:
        host_port = _published_loopback_port(engine, name, port)
        _probe_loopback(host_port, service, path=health_path)
        # The user-visible lease starts only after the exact loopback identity
        # probe succeeds. The startup watchdog is superseded by this final
        # epoch-bound marker and therefore cannot shorten the usable 600s.
        lease_started_epoch = int(time.time()) + 1
        lease_expires_epoch = lease_started_epoch + lease_seconds
        watchdog_pid = _start_expiry_watchdog(
            engine,
            language,
            arguments.job_id,
            lease_expires_epoch,
            lease_id,
            state,
        )
        _write_lease_marker(
            state,
            arguments.job_id,
            language,
            lease_id,
            lease_started_epoch=lease_started_epoch,
            lease_expires_epoch=lease_expires_epoch,
        )
    except RunnerError:
        try:
            _stop_locked(cleanup_arguments)
        except RunnerError:
            pass
        raise
    return {
        "status": "RUNNING",
        "executor": "ROOTLESS_CONTAINER",
        "container_name": name,
        "container_id": start.stdout.strip(),
        "image": image,
        "workspace": str(workspace),
        "runtime_network": names["network"],
        "network_policy": "internal-only-no-external-egress",
        "loopback_url": f"http://127.0.0.1:{host_port}",
        "host_port": host_port,
        "persistence": persistence,
        "auth_mode": auth_mode,
        "health": "loopback-identity-verified",
        "read_only": True,
        "user": runtime_user,
        "limits": {"cpus": 0.5, "memory": "512m", "pids": 256},
        "lease_seconds": lease_seconds,
        "lease_started_epoch": lease_started_epoch,
        "lease_expires_epoch": lease_expires_epoch,
        "lease_id": lease_id,
        "watchdog_pid": watchdog_pid,
    }


def _start(arguments: argparse.Namespace) -> dict[str, Any]:
    with _runtime_operation_lock(arguments):
        return _start_locked(arguments)


def _status_locked(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    _preflight(engine)
    name = _container_name(arguments.job_id, arguments.language)
    result = _run(
        [
            str(engine),
            "inspect",
            "--format",
            "{{json .State}}",
            name,
        ],
        timeout=20,
    )
    if result.returncode != 0:
        return {"status": "MISSING", "container_name": name}
    state = json.loads(result.stdout)
    running = bool(state.get("Running"))
    health = "not-running"
    status = "BLOCKED"
    if running:
        labels_result = _run(
            [
                str(engine),
                "inspect",
                "--format",
                "{{json .Config.Labels}}",
                name,
            ],
            timeout=20,
        )
        if labels_result.returncode != 0:
            raise RunnerError("CONTAINER_LABELS_UNAVAILABLE")
        labels = json.loads(labels_result.stdout)
        service = labels.get("io.elmos.service") if isinstance(labels, dict) else None
        port_value = labels.get("io.elmos.port") if isinstance(labels, dict) else None
        persistence = labels.get("io.elmos.persistence") if isinstance(labels, dict) else None
        lease_value = labels.get("io.elmos.lease-seconds") if isinstance(labels, dict) else None
        lease_id = labels.get("io.elmos.lease-id") if isinstance(labels, dict) else None
        job_value = labels.get("io.elmos.job") if isinstance(labels, dict) else None
        language_value = labels.get("io.elmos.language") if isinstance(labels, dict) else None
        expected_port = PORTS[arguments.language]
        if (
            not isinstance(service, str)
            or IDENTIFIER.fullmatch(service) is None
            or port_value != str(expected_port)
            or persistence not in {"in-memory", "postgresql"}
            or not isinstance(lease_value, str)
            or not lease_value.isdigit()
            or not 1 <= int(lease_value) <= 600
            or not isinstance(lease_id, str)
            or LEASE_ID.fullmatch(lease_id) is None
            or job_value != arguments.job_id
            or language_value != arguments.language
        ):
            raise RunnerError("CONTAINER_IDENTITY_LABELS_INVALID")
        expected_lease_id = getattr(arguments, "lease_id", None)
        if expected_lease_id and expected_lease_id != lease_id:
            return {
                "status": "SUPERSEDED",
                "container_name": name,
                "health": "newer-runtime-lease-active",
                "lease_id": lease_id,
                "exit_code": state.get("ExitCode"),
            }
        marker = _read_lease_marker(getattr(arguments, "state", None))
        if (
            marker is None
            or marker["job_id"] != arguments.job_id
            or marker["language"] != arguments.language
            or marker["lease_id"] != lease_id
            or marker.get("phase") != "RUNNING"
        ):
            raise RunnerError("RUNTIME_LEASE_MARKER_INVALID")
        expires_value = marker["lease_expires_epoch"]
        if expires_value <= int(time.time()):
            stopped = _stop_locked(arguments)
            if stopped.get("status") != "STOPPED":
                return stopped
            return {
                "status": "EXPIRED",
                "container_name": name,
                "health": "lease-expired-cleaned",
                "exit_code": state.get("ExitCode"),
            }
        try:
            health_path = "/health/ready" if persistence == "postgresql" else "/health"
            host_port = _published_loopback_port(engine, name, expected_port)
            _probe_loopback(host_port, service, path=health_path, timeout=2.0)
            status = "RUNNING"
            health = "loopback-identity-verified"
        except RunnerError:
            status = "STARTING"
            health = "loopback-probe-pending"
    return {
        "status": status,
        "container_name": name,
        "health": health,
        "exit_code": state.get("ExitCode"),
        **({"host_port": host_port} if running and status == "RUNNING" else {}),
    }


def _status(arguments: argparse.Namespace) -> dict[str, Any]:
    with _runtime_operation_lock(arguments):
        return _status_locked(arguments)


def _stop_receipt(
    arguments: argparse.Namespace,
    status: str,
    container_name: str,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "status": status,
        "container_name": container_name,
        "job_id": arguments.job_id,
        "language": arguments.language,
    }
    requested_lease_id = getattr(arguments, "lease_id", None)
    if requested_lease_id:
        receipt["requested_lease_id"] = requested_lease_id
    return receipt


def _stop_locked(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    _preflight(engine)
    names = _runtime_names(arguments.job_id, arguments.language)
    name = names["application"]
    image = f"localhost/elmos/{name}:local"
    expected_lease_id = getattr(arguments, "lease_id", None)
    if expected_lease_id and LEASE_ID.fullmatch(expected_lease_id) is None:
        raise RunnerError("RUNTIME_LEASE_ID_INVALID")
    marker = _read_lease_marker(getattr(arguments, "state", None))
    expected_expires_epoch = getattr(arguments, "expires_epoch", None)
    if marker is not None and (
        marker["job_id"] != arguments.job_id
        or marker["language"] != arguments.language
        or (expected_lease_id and marker["lease_id"] != expected_lease_id)
        or (
            expected_expires_epoch is not None
            and marker.get("lease_expires_epoch") != expected_expires_epoch
        )
    ):
        return _stop_receipt(arguments, "SUPERSEDED", name)
    resources = (
        ("container", name),
        ("container", names["database"]),
        ("network", names["network"]),
        ("volume", names["volume"]),
        ("image", image),
    )
    observed = {
        (kind, resource): _resource_labels(engine, kind, resource)
        for kind, resource in resources
    }
    existing = [labels for labels in observed.values() if labels is not None]
    if not existing and marker is None:
        return _stop_receipt(arguments, "MISSING", name)
    authoritative_lease_id = expected_lease_id or (marker["lease_id"] if marker else None)
    if authoritative_lease_id is None and existing:
        candidate_ids = {labels.get("io.elmos.lease-id") for labels in existing}
        if len(candidate_ids) != 1:
            raise RunnerError("RUNTIME_RESOURCE_LEASE_IDENTITY_INVALID")
        authoritative_lease_id = next(iter(candidate_ids))
    if not isinstance(authoritative_lease_id, str) or LEASE_ID.fullmatch(authoritative_lease_id) is None:
        raise RunnerError("RUNTIME_RESOURCE_LEASE_IDENTITY_INVALID")
    if any(
        not _resource_identity_matches(
            labels,
            arguments.job_id,
            arguments.language,
            authoritative_lease_id,
        )
        for labels in existing
    ):
        if expected_lease_id and any(
            labels.get("io.elmos.lease-id") != expected_lease_id for labels in existing
        ):
            return _stop_receipt(arguments, "SUPERSEDED", name)
        raise RunnerError("RUNTIME_RESOURCE_IDENTITY_INVALID")
    result = _run([str(engine), "rm", "--force", name], timeout=30)
    if result.returncode != 0 and "no such" not in (result.stderr + result.stdout).lower():
        raise RunnerError("CONTAINER_STOP_FAILED")
    database = _run([str(engine), "rm", "--force", names["database"]], timeout=30)
    if database.returncode != 0 and "no such" not in (database.stderr + database.stdout).lower():
        raise RunnerError("DATABASE_CONTAINER_STOP_FAILED")
    network = _run([str(engine), "network", "rm", names["network"]], timeout=30)
    if network.returncode != 0 and "no such" not in (network.stderr + network.stdout).lower():
        raise RunnerError("INTERNAL_NETWORK_REMOVE_FAILED")
    volume = _run([str(engine), "volume", "rm", "--force", names["volume"]], timeout=30)
    if volume.returncode != 0 and "no such" not in (volume.stderr + volume.stdout).lower():
        raise RunnerError("DATABASE_VOLUME_REMOVE_FAILED")
    image_result = _run([str(engine), "image", "rm", "--force", image], timeout=60)
    if image_result.returncode != 0 and "no such" not in (image_result.stderr + image_result.stdout).lower():
        raise RunnerError("RUNTIME_IMAGE_REMOVE_FAILED")
    raw_state = getattr(arguments, "state", None)
    if raw_state:
        state = Path(raw_state)
        if not state.exists():
            return _stop_receipt(arguments, "STOPPED", name)
        if not state.is_absolute() or state.is_symlink() or not state.is_dir():
            raise RunnerError("RUNTIME_STATE_INVALID")
        resolved_state = state.resolve(strict=True)
        if resolved_state.stat().st_mode & 0o077:
            raise RunnerError("RUNTIME_STATE_INVALID")
        allowed = {
            "database-url",
            "jwt-hmac-secret",
            "oidc-jwks",
            "oidc-private-key.pem",
            "postgres-admin-password",
            "postgres-runtime-password",
            "lease.json",
        }
        entries = list(resolved_state.iterdir())
        if any(
            (
                entry.name not in allowed
                and re.fullmatch(r"\.lease-[0-9a-f]{16}\.tmp", entry.name) is None
            )
            or entry.is_symlink()
            or not entry.is_file()
            for entry in entries
        ):
            raise RunnerError("RUNTIME_STATE_CLEANUP_UNSAFE")
        for entry in entries:
            entry.unlink()
        resolved_state.rmdir()
    if any(_resource_labels(engine, kind, resource) is not None for kind, resource in resources):
        raise RunnerError("RUNTIME_RESOURCE_CLEANUP_UNVERIFIED")
    return _stop_receipt(arguments, "STOPPED", name)


def _stop(arguments: argparse.Namespace) -> dict[str, Any]:
    with _runtime_operation_lock(arguments):
        return _stop_locked(arguments)


def _start_expiry_watchdog(
    engine: Path,
    language: str,
    job_id: str,
    expires_epoch: int,
    lease_id: str,
    state: Path,
) -> int:
    if LEASE_ID.fullmatch(lease_id) is None:
        raise RunnerError("RUNTIME_LEASE_ID_INVALID")
    script = Path(__file__).resolve(strict=True)
    try:
        watchdog = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                str(script),
                "expire",
                "--engine",
                str(engine),
                "--language",
                language,
                "--job-id",
                job_id,
                "--expires-epoch",
                str(expires_epoch),
                "--lease-id",
                lease_id,
                "--state",
                str(state),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as error:
        raise RunnerError("RUNTIME_LEASE_WATCHDOG_START_FAILED") from error
    if watchdog.pid <= 0:
        raise RunnerError("RUNTIME_LEASE_WATCHDOG_START_FAILED")
    return watchdog.pid


def _expire(arguments: argparse.Namespace) -> dict[str, Any]:
    remaining = arguments.expires_epoch - time.time()
    if remaining > 605:
        raise RunnerError("RUNTIME_LEASE_EXPIRY_INVALID")
    if remaining > 0:
        time.sleep(remaining)
    failure: BaseException | None = None
    for attempt in range(3):
        try:
            with _runtime_operation_lock(arguments):
                result = _stop_locked(arguments)
            if result.get("status") != "STOPPED":
                return result
            return {**result, "status": "EXPIRED"}
        except (
            RunnerError,
            OSError,
            ValueError,
            json.JSONDecodeError,
            subprocess.SubprocessError,
        ) as error:
            failure = error
            if attempt < 2:
                time.sleep(2**attempt)
    raise RunnerError("RUNTIME_LEASE_CLEANUP_FAILED") from failure


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)
    preflight = subcommands.add_parser("preflight")
    preflight.add_argument("--engine", required=True)
    diagnose = subcommands.add_parser("diagnose")
    diagnose.add_argument("--engine", required=True)
    diagnose.add_argument("--workspace", required=True)
    diagnose.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    diagnose.add_argument("--build-network", default="none")
    start = subcommands.add_parser("start")
    start.add_argument("--engine", required=True)
    start.add_argument("--workspace", required=True)
    start.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    start.add_argument("--port", type=int, required=True)
    start.add_argument("--job-id", required=True)
    start.add_argument("--service", required=True)
    start.add_argument("--state", required=True)
    start.add_argument("--persistence", choices=["in-memory", "postgresql"], required=True)
    start.add_argument("--auth-mode", choices=["none", "jwt", "oidc"], required=True)
    start.add_argument("--build-network", default="none")
    start.add_argument("--lease-seconds", type=int, default=600)
    status = subcommands.add_parser("status")
    status.add_argument("--engine", required=True)
    status.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    status.add_argument("--job-id", required=True)
    status.add_argument("--state", required=True)
    status.add_argument("--lease-id")
    stop = subcommands.add_parser("stop")
    stop.add_argument("--engine", required=True)
    stop.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    stop.add_argument("--job-id", required=True)
    stop.add_argument("--state", required=True)
    stop.add_argument("--lease-id")
    expire = subcommands.add_parser("expire")
    expire.add_argument("--engine", required=True)
    expire.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    expire.add_argument("--job-id", required=True)
    expire.add_argument("--expires-epoch", type=int, required=True)
    expire.add_argument("--state", required=True)
    expire.add_argument("--lease-id", required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        result = {
            "preflight": lambda: _preflight(Path(arguments.engine)),
            "diagnose": lambda: _diagnose(arguments),
            "start": lambda: _start(arguments),
            "status": lambda: _status(arguments),
            "stop": lambda: _stop(arguments),
            "expire": lambda: _expire(arguments),
        }[arguments.command]()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError, RunnerError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}), file=sys.stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
