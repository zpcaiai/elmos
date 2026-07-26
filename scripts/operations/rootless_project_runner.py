#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from typing import Any
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
    return f"elmos-{job_id[:12]}-{language}"


def _runtime_names(job_id: str, language: str) -> dict[str, str]:
    application = _container_name(job_id, language)
    return {
        "application": application,
        "database": f"{application}-postgres",
        "network": f"{application}-internal",
        "volume": f"{application}-postgres-data",
    }


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


def _create_internal_network(engine: Path, network: str, job_id: str) -> None:
    result = _run(
        [
            str(engine),
            "network",
            "create",
            "--internal",
            "--label",
            f"io.elmos.job={job_id}",
            network,
        ],
        timeout=30,
    )
    if result.returncode != 0 and "already exists" not in (result.stderr + result.stdout).lower():
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
    if port not in PORTS.values() or IDENTIFIER.fullmatch(service) is None:
        raise RunnerError("HEALTH_IDENTITY_INVALID")
    if path not in {"/health", "/health/ready"}:
        raise RunnerError("HEALTH_PATH_INVALID")
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(  # noqa: S310
                f"http://127.0.0.1:{port}{path}",
                method="GET",
            )
            with opener.open(request, timeout=1) as response:
                payload = json.loads(response.read().decode("utf-8"))
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


def _setup_postgresql(
    engine: Path,
    *,
    workspace: Path,
    state: Path,
    names: dict[str, str],
    job_id: str,
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
    _run([str(engine), "rm", "--force", names["database"]], timeout=30)
    volume = _run(
        [
            str(engine),
            "volume",
            "create",
            "--label",
            f"io.elmos.job={job_id}",
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


def _start(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    _preflight(engine)
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
    _validate_build_network(engine, build_network)
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
            "--tag",
            image,
            str(target),
        ]
    )
    if build.returncode != 0:
        raise RunnerError(f"CONTAINER_BUILD_FAILED:{(build.stderr or build.stdout)[-2000:]}")
    _create_internal_network(engine, names["network"], arguments.job_id)
    _run([str(engine), "rm", "--force", name], timeout=30)
    provider_arguments = (
        _setup_postgresql(
            engine,
            workspace=workspace,
            state=state,
            names=names,
            job_id=arguments.job_id,
        )
        if persistence == "postgresql"
        else []
    )
    authentication_arguments = _authentication_arguments(state, auth_mode)
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
            "--network",
            names["network"],
            "--publish",
            f"127.0.0.1:{port}:{port}",
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
        raise RunnerError(f"CONTAINER_START_FAILED:{(start.stderr or start.stdout)[-2000:]}")
    health_path = "/health/ready" if persistence == "postgresql" else "/health"
    try:
        _probe_loopback(port, service, path=health_path)
    except RunnerError:
        _run([str(engine), "rm", "--force", name], timeout=30)
        _run([str(engine), "rm", "--force", names["database"]], timeout=30)
        _run([str(engine), "network", "rm", names["network"]], timeout=30)
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
        "loopback_url": f"http://127.0.0.1:{port}",
        "persistence": persistence,
        "auth_mode": auth_mode,
        "health": "loopback-identity-verified",
        "read_only": True,
        "user": runtime_user,
        "limits": {"cpus": 0.5, "memory": "512m", "pids": 256},
    }


def _status(arguments: argparse.Namespace) -> dict[str, Any]:
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
        expected_port = PORTS[arguments.language]
        if (
            not isinstance(service, str)
            or IDENTIFIER.fullmatch(service) is None
            or port_value != str(expected_port)
            or persistence not in {"in-memory", "postgresql"}
        ):
            raise RunnerError("CONTAINER_IDENTITY_LABELS_INVALID")
        try:
            health_path = "/health/ready" if persistence == "postgresql" else "/health"
            _probe_loopback(expected_port, service, path=health_path, timeout=2.0)
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
    }


def _stop(arguments: argparse.Namespace) -> dict[str, Any]:
    engine = Path(arguments.engine)
    _preflight(engine)
    names = _runtime_names(arguments.job_id, arguments.language)
    name = names["application"]
    result = _run([str(engine), "rm", "--force", name], timeout=30)
    if result.returncode != 0 and "no such" not in (result.stderr + result.stdout).lower():
        raise RunnerError("CONTAINER_STOP_FAILED")
    _run([str(engine), "rm", "--force", names["database"]], timeout=30)
    network = _run([str(engine), "network", "rm", names["network"]], timeout=30)
    if network.returncode != 0 and "no such" not in (network.stderr + network.stdout).lower():
        raise RunnerError("INTERNAL_NETWORK_REMOVE_FAILED")
    return {"status": "STOPPED", "container_name": name}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    subcommands = root.add_subparsers(dest="command", required=True)
    preflight = subcommands.add_parser("preflight")
    preflight.add_argument("--engine", required=True)
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
    status = subcommands.add_parser("status")
    status.add_argument("--engine", required=True)
    status.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    status.add_argument("--job-id", required=True)
    stop = subcommands.add_parser("stop")
    stop.add_argument("--engine", required=True)
    stop.add_argument("--language", choices=sorted(LANGUAGE_DIRECTORIES), required=True)
    stop.add_argument("--job-id", required=True)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        result = {
            "preflight": lambda: _preflight(Path(arguments.engine)),
            "start": lambda: _start(arguments),
            "status": lambda: _status(arguments),
            "stop": lambda: _stop(arguments),
        }[arguments.command]()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError, RunnerError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}), file=sys.stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
