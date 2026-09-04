#!/usr/bin/env python3
"""Fail-closed checks for the dedicated Spring production Runner topology.

Static validation is repository engineering evidence only.  ``--check-host``
adds read-only checks against a prepared rootless Linux host, while
``--check-running`` also inspects already-running Compose resources.  None of
the modes creates external evidence or changes certification state.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as error:  # pragma: no cover - exercised by CLI environments
    raise SystemExit("PyYAML is required; run with `uv run --with pyyaml`") from error


ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ContractPaths:
    runner_compose: Path = ROOT / "deploy/production/compose/docker-compose.spring-runner.yml"
    application_compose: Path = ROOT / "deploy/production/compose/docker-compose.production.yml"
    application_spring_overlay: Path = (
        ROOT / "deploy/production/compose/docker-compose.spring-application.yml"
    )
    ingress_config: Path = ROOT / "deploy/production/runner/nginx.spring-runner.conf"
    runner_environment_example: Path = ROOT / "deploy/production/runner/spring-runner.env.example"
    spring_launch_environment_example: Path = (
        ROOT / "deploy/production/spring-launch.env.example"
    )
    environment_example: Path = ROOT / "deploy/production/elmos-commercial.env.example"
    rootless_readme: Path = ROOT / "deploy/rootless-docker/README.md"
    production_readme: Path = ROOT / "deploy/production/README.md"


IMAGE_ENVIRONMENTS = (
    "ELMOS_SPRING_INGRESS_IMAGE",
    "ELMOS_SPRING_WORKSPACE_SERVICE_IMAGE",
    "ELMOS_SPRING_EGRESS_PROXY_IMAGE",
)
CHILD_IMAGE_DIGEST_ENVIRONMENTS = (
    "ELMOS_SNAPSHOT_HELPER_IMAGE_DIGEST",
    "ELMOS_EGRESS_PROXY_IMAGE_DIGEST",
    "ELMOS_JAVA_RUNTIME_IMAGE_DIGEST",
    "ELMOS_SPRING_VERIFIER_IMAGE_DIGEST",
    "ELMOS_SPRING_TRANSFORMER_IMAGE_DIGEST",
)
BROKER_SECRET_ENVIRONMENTS = (
    "ELMOS_SPRING_BROKER_VERIFIER_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_BROKER_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_BROKER_RUNTIME_HMAC_SECRET_HOST_PATH",
)
APPLICATION_SECRET_ENVIRONMENTS = (
    "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
    "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
)
ENGINE_SECRET_ENVIRONMENT = "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"
ENGINE_REPLAY_ENVIRONMENT = "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH"
RUNNER_REPLAY_ENVIRONMENT = "ELMOS_SPRING_RUNNER_REPLAY_HOST_PATH"
WORKER_PATH_OVERRIDE_ENVIRONMENTS = (
    "SPRING_APPLICATION_JSON",
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "JAVA_OPTS",
    "JDK_JAVA_OPTIONS",
    "SERVER_SERVLET_CONTEXT_PATH",
    "SERVER_SERVLET_PATH",
    "SPRING_MVC_SERVLET_PATH",
)
BROKER_PATHS = (
    "/internal/v1/spring-transformations",
    "/internal/v1/spring-verifications",
    "/internal/v1/spring-runtimes",
)
BROKER_BODY_LIMITS = {
    "/internal/v1/spring-transformations": "128k",
    "/internal/v1/spring-verifications": "64k",
    "/internal/v1/spring-runtimes": "64k",
}
EXPECTED_INGRESS_CONFIG_SHA256 = (
    "8547df2235fb8bc0a516f1aefbda9a2c23f06f8afcef8d4c5e3d108295c930f7"
)
EXPECTED_RUNNER_SERVICES = {
    "spring-runner-ingress",
    "spring-runner-broker",
    "spring-runner-egress-proxy",
}
SERVICE_IMAGE_ENVIRONMENTS = {
    "spring-runner-ingress": "ELMOS_SPRING_INGRESS_IMAGE",
    "spring-runner-broker": "ELMOS_SPRING_WORKSPACE_SERVICE_IMAGE",
    "spring-runner-egress-proxy": "ELMOS_SPRING_EGRESS_PROXY_IMAGE",
}
SERVICE_USERS = {
    "spring-runner-ingress": "10004:10004",
    "spring-runner-broker": "10001:10001",
    "spring-runner-egress-proxy": "10001:10001",
}
OPERATIONAL_ROOT_ENVIRONMENTS = (
    "ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH",
    "ELMOS_COMMAND_ARTIFACT_HOST_PATH",
    "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    "ELMOS_VERIFIER_EVIDENCE_HOST_PATH",
    RUNNER_REPLAY_ENVIRONMENT,
)
SENSITIVE_PATH_ENVIRONMENTS = (
    "ELMOS_SPRING_BROKER_SECRET_ROOT",
    "ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT",
    "ELMOS_SPRING_INGRESS_TLS_KEY_HOST_PATH",
    "ELMOS_SPRING_RUNNER_ENV_FILE",
) + BROKER_SECRET_ENVIRONMENTS
RUNNER_SERVICE_ENVIRONMENT_CONTRACT: dict[str, dict[str, str]] = {
    "spring-runner-ingress": {},
    "spring-runner-broker": {
        "ELMOS_DATABASE_URL": "${ELMOS_SPRING_RUNNER_DATABASE_URL:?runner database URL is required}",
        "ELMOS_DATABASE_USER": "${ELMOS_SPRING_RUNNER_DATABASE_USER:?runner database user is required}",
        "ELMOS_DATABASE_PASSWORD": "${ELMOS_SPRING_RUNNER_DATABASE_PASSWORD:?runner database password is required}",
        "ELMOS_WORKSPACE_DOCKER_ENABLED": "true",
        "ELMOS_WORKSPACE_SECRETS_ENABLED": "false",
        "ELMOS_SNAPSHOT_ARTIFACT_ROOT": "/var/lib/elmos/snapshot-artifacts",
        "ELMOS_COMMAND_ARTIFACT_ROOT": "/var/lib/elmos/command-artifacts",
        "ELMOS_SNAPSHOT_HELPER_IMAGE_DIGEST": "${ELMOS_SNAPSHOT_HELPER_IMAGE_DIGEST:?snapshot helper digest is required}",
        "ELMOS_EGRESS_PROXY_IMAGE_DIGEST": "${ELMOS_EGRESS_PROXY_IMAGE_DIGEST:?egress proxy digest is required}",
        "ELMOS_SPRING_RUNTIME_ENABLED": "true",
        "ELMOS_JAVA_RUNTIME_IMAGE_DIGEST": "${ELMOS_JAVA_RUNTIME_IMAGE_DIGEST:?runtime digest is required}",
        "ELMOS_JAVA_UPGRADE_ARTIFACT_ROOT": "/var/lib/elmos/java-verifier-evidence",
        "ELMOS_JAVA_UPGRADE_ARTIFACT_HOST_ROOT": "${ELMOS_VERIFIER_EVIDENCE_HOST_PATH:?evidence host root is required}",
        "ELMOS_SPRING_RUNTIME_HMAC_SECRET_FILE": "/run/secrets/elmos-runtime-hmac",
        "ELMOS_SPRING_RUNTIME_REPLAY_ROOT": "/var/lib/elmos/spring-auth-replay/runtime",
        "ELMOS_EPHEMERAL_SPRING_VERIFIER_ENABLED": "true",
        "ELMOS_SPRING_VERIFIER_IMAGE_DIGEST": "${ELMOS_SPRING_VERIFIER_IMAGE_DIGEST:?verifier digest is required}",
        "ELMOS_SPRING_VERIFIER_ID": "${ELMOS_SPRING_UPGRADE_VERIFIER_ID:?verifier identity is required}",
        "ELMOS_JAVA_UPGRADE_INTERNAL_NETWORK": "elmos-spring-runner-broker",
        "ELMOS_JAVA_UPGRADE_EGRESS_PROXY_URL": "http://spring-runner-egress-proxy:8080",
        "ELMOS_SPRING_VERIFIER_SERVICE_INPUT_ROOT": "/var/lib/elmos/java-upgrade-runs",
        "ELMOS_SPRING_VERIFIER_HOST_INPUT_ROOT": "${ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH:?shared workspace is required}",
        "ELMOS_SPRING_VERIFIER_SERVICE_EVIDENCE_ROOT": "/var/lib/elmos/java-verifier-evidence",
        "ELMOS_SPRING_VERIFIER_HOST_EVIDENCE_ROOT": "${ELMOS_VERIFIER_EVIDENCE_HOST_PATH:?evidence host root is required}",
        "ELMOS_SPRING_VERIFIER_HMAC_SECRET_FILE": "/run/secrets/elmos-verifier-hmac",
        "ELMOS_SPRING_VERIFIER_REPLAY_ROOT": "/var/lib/elmos/spring-auth-replay/verifier",
        "ELMOS_EPHEMERAL_SPRING_TRANSFORMER_ENABLED": "true",
        "ELMOS_SPRING_TRANSFORMER_IMAGE_DIGEST": "${ELMOS_SPRING_TRANSFORMER_IMAGE_DIGEST:?transformer digest is required}",
        "ELMOS_SPRING_TRANSFORMER_SERVICE_RUN_ROOT": "/var/lib/elmos/java-upgrade-runs",
        "ELMOS_SPRING_TRANSFORMER_HOST_RUN_ROOT": "${ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH:?shared workspace is required}",
        "ELMOS_SPRING_TRANSFORMER_HMAC_SECRET_FILE": "/run/secrets/elmos-transformer-hmac",
        "ELMOS_SPRING_TRANSFORMER_REPLAY_ROOT": "/var/lib/elmos/spring-auth-replay/transformer",
        "ELMOS_ALLOWED_GIT_HOSTS": "${ELMOS_ALLOWED_GIT_HOSTS:-github.com}",
        "ELMOS_SHUTDOWN_TIMEOUT": "30s",
    },
    "spring-runner-egress-proxy": {
        "ELMOS_PROXY_PORT": "8080",
        "ELMOS_WORKSPACE_ID": "spring-production-runner",
        "ELMOS_NETWORK_POLICY_ID": "spring-production-default-deny",
        "ELMOS_NETWORK_POLICY_VERSION": "${ELMOS_NETWORK_POLICY_VERSION:?approved policy version is required}",
        "ELMOS_EGRESS_ALLOWED_HOSTS": "${ELMOS_JAVA_UPGRADE_EGRESS_HOSTS:-github.com,api.github.com,objects.githubusercontent.com}",
    },
}
RUNNER_SERVICE_MOUNT_CONTRACT: dict[str, dict[str, tuple[str, bool]]] = {
    "spring-runner-ingress": {
        "/etc/nginx/nginx.conf": ("ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH", False),
        "/run/secrets/tls/tls.crt": ("ELMOS_SPRING_INGRESS_TLS_CERT_HOST_PATH", False),
        "/run/secrets/tls/tls.key": ("ELMOS_SPRING_INGRESS_TLS_KEY_HOST_PATH", False),
    },
    "spring-runner-broker": {
        "/run/docker.sock": ("ELMOS_ROOTLESS_DOCKER_SOCKET", True),
        "/var/lib/elmos/snapshot-artifacts": ("ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH", False),
        "/var/lib/elmos/command-artifacts": ("ELMOS_COMMAND_ARTIFACT_HOST_PATH", True),
        "/var/lib/elmos/java-upgrade-runs": ("ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH", False),
        "/var/lib/elmos/java-verifier-evidence": ("ELMOS_VERIFIER_EVIDENCE_HOST_PATH", True),
        "/run/secrets/elmos-runtime-hmac": ("ELMOS_SPRING_BROKER_RUNTIME_HMAC_SECRET_HOST_PATH", False),
        "/run/secrets/elmos-verifier-hmac": ("ELMOS_SPRING_BROKER_VERIFIER_HMAC_SECRET_HOST_PATH", False),
        "/run/secrets/elmos-transformer-hmac": ("ELMOS_SPRING_BROKER_TRANSFORMER_HMAC_SECRET_HOST_PATH", False),
        "/var/lib/elmos/spring-auth-replay": (RUNNER_REPLAY_ENVIRONMENT, True),
    },
    "spring-runner-egress-proxy": {},
}
RUNNER_SERVICE_TMPFS_CONTRACT = {
    "spring-runner-ingress": ["/tmp:rw,noexec,nosuid,size=32m"],
    "spring-runner-broker": ["/tmp:rw,noexec,nosuid,size=256m"],
    "spring-runner-egress-proxy": ["/tmp:rw,noexec,nosuid,size=32m"],
}
RUNNER_SERVICE_RESOURCE_CONTRACT = {
    "spring-runner-ingress": {"mem_limit": "256m", "cpus": 1, "pids_limit": 128},
    "spring-runner-broker": {"mem_limit": "4g", "cpus": 4, "pids_limit": 512},
    "spring-runner-egress-proxy": {"mem_limit": "512m", "cpus": 1, "pids_limit": 128},
}
RUNNER_SERVICE_HEALTHCHECK_CONTRACT: dict[str, dict[str, Any] | None] = {
    "spring-runner-ingress": {
        "test": ["CMD", "nginx", "-t", "-c", "/etc/nginx/nginx.conf"],
        "interval": "15s",
        "timeout": "3s",
        "retries": 4,
        "start_period": "10s",
    },
    "spring-runner-broker": {
        "test": ["CMD", "bash", "-ec", "exec 3<>/dev/tcp/127.0.0.1/8082"],
        "interval": "10s",
        "timeout": "3s",
        "retries": 10,
        "start_period": "20s",
    },
    "spring-runner-egress-proxy": None,
}
RUNNER_LOGGING_CONTRACT = {
    "driver": "json-file",
    "options": {"max-size": "20m", "max-file": "5"},
}
RUNNER_SERVICE_RUNTIME_RESOURCE_CONTRACT = {
    "spring-runner-ingress": {"Memory": 256 * 1024 * 1024, "NanoCpus": 1_000_000_000},
    "spring-runner-broker": {"Memory": 4 * 1024 * 1024 * 1024, "NanoCpus": 4_000_000_000},
    "spring-runner-egress-proxy": {"Memory": 512 * 1024 * 1024, "NanoCpus": 1_000_000_000},
}
RUNNER_SERVICE_TMPFS_SIZE_CONTRACT = {
    "spring-runner-ingress": {"32m", str(32 * 1024 * 1024)},
    "spring-runner-broker": {"256m", str(256 * 1024 * 1024)},
    "spring-runner-egress-proxy": {"32m", str(32 * 1024 * 1024)},
}
RUNNER_ENVIRONMENT_ALLOWLIST = frozenset(
    IMAGE_ENVIRONMENTS
    + CHILD_IMAGE_DIGEST_ENVIRONMENTS
    + BROKER_SECRET_ENVIRONMENTS
    + (
        "ELMOS_ALLOWED_GIT_HOSTS",
        "ELMOS_COMMAND_ARTIFACT_HOST_PATH",
        "ELMOS_JAVA_UPGRADE_EGRESS_HOSTS",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
        "ELMOS_NETWORK_POLICY_VERSION",
        "ELMOS_ROOTLESS_DOCKER_SOCKET",
        "ELMOS_ROOTLESS_UID",
        "ELMOS_ROOTLESS_GID",
        "ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH",
        "ELMOS_SPRING_BROKER_SECRET_ROOT",
        "ELMOS_SPRING_BROKER_SECRET_MAPPED_UID",
        "ELMOS_SPRING_BROKER_SECRET_MAPPED_GID",
        "ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH",
        "ELMOS_SPRING_INGRESS_TLS_CERT_HOST_PATH",
        "ELMOS_SPRING_INGRESS_TLS_KEY_HOST_PATH",
        "ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT",
        "ELMOS_SPRING_INGRESS_SECRET_MAPPED_UID",
        "ELMOS_SPRING_INGRESS_SECRET_MAPPED_GID",
        "ELMOS_SPRING_RUNNER_CONTROL_NETWORK",
        "ELMOS_SPRING_RUNNER_DATABASE_PASSWORD",
        "ELMOS_SPRING_RUNNER_DATABASE_URL",
        "ELMOS_SPRING_RUNNER_DATABASE_USER",
        "ELMOS_SPRING_RUNNER_ENV_FILE",
        "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS",
        "ELMOS_SPRING_RUNNER_HTTPS_PORT",
        RUNNER_REPLAY_ENVIRONMENT,
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
        "ELMOS_VERIFIER_EVIDENCE_HOST_PATH",
    )
)
PINNED_IMAGE = re.compile(r"^[^\s@]+(?::[^\s@]+)?@sha256:[0-9a-f]{64}$")
SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
ENVIRONMENT_NAME = re.compile(r"^ELMOS_[A-Z0-9_]+$")
ENVIRONMENT_VALUE = re.compile(r"^[A-Za-z0-9_./:@?=,+%&\[\]-]+$")
COMPOSE_INTERPOLATION = re.compile(
    r"^\$\{(?P<name>[A-Z][A-Z0-9_]*)(?::(?P<operator>[-?])(?P<fallback>.*))?\}$"
)


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path}: expected YAML object")
    return value


def require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def service_networks(service: Mapping[str, Any]) -> set[str]:
    networks = service.get("networks", [])
    if isinstance(networks, dict):
        return set(networks)
    if isinstance(networks, list):
        return {item for item in networks if isinstance(item, str)}
    return set()


def service_volumes(service: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    volumes = service.get("volumes", [])
    if not isinstance(volumes, list):
        return result
    for item in volumes:
        if isinstance(item, dict):
            result.append(dict(item))
            continue
        if isinstance(item, str):
            fields = item.split(":")
            if len(fields) >= 2:
                result.append(
                    {
                        "type": "bind",
                        "source": fields[0],
                        "target": fields[1],
                        "read_only": "ro" in fields[2:],
                    }
                )
    return result


def volume_for_target(service: Mapping[str, Any], target: str) -> dict[str, Any] | None:
    return next((item for item in service_volumes(service) if item.get("target") == target), None)


def validate_hardening(errors: list[str], name: str, service: Mapping[str, Any]) -> None:
    require(errors, service.get("init") is True, f"{name} must run with an init process")
    require(errors, service.get("restart") == "unless-stopped", f"{name} restart policy drift")
    require(errors, service.get("read_only") is True, f"{name} root filesystem must be read-only")
    require(errors, service.get("privileged") in (None, False), f"{name} must not be privileged")
    require(errors, service.get("cap_add") in (None, []), f"{name} must not add capabilities")
    require(errors, service.get("cap_drop") == ["ALL"], f"{name} must drop all capabilities")
    require(
        errors,
        service.get("security_opt") == ["no-new-privileges:true"],
        f"{name} must enable only no-new-privileges",
    )
    require(
        errors,
        isinstance(service.get("pids_limit"), int)
        and not isinstance(service.get("pids_limit"), bool)
        and service["pids_limit"] > 0,
        f"{name} must have a positive PID limit",
    )
    for field in (
        "network_mode",
        "pid",
        "ipc",
        "uts",
        "userns_mode",
        "devices",
        "device_cgroup_rules",
        "volumes_from",
        "extra_hosts",
        "dns",
    ):
        require(errors, field not in service, f"{name} must not override {field}")


def validate_runner_compose(errors: list[str], compose: Mapping[str, Any]) -> None:
    services = compose.get("services", {})
    networks = compose.get("networks", {})
    require(errors, compose.get("name") == "elmos-spring-runner", "runner Compose must use an explicit project name")
    require(errors, isinstance(services, dict), "runner Compose services must be an object")
    if not isinstance(services, dict):
        return
    require(errors, set(services) == EXPECTED_RUNNER_SERVICES, "runner security-domain service inventory drift")
    for name in EXPECTED_RUNNER_SERVICES:
        service = services.get(name, {})
        if not isinstance(service, dict):
            errors.append(f"runner service {name} is missing")
            continue
        validate_hardening(errors, name, service)
        require(
            errors,
            "env_file" not in service,
            f"{name} must not receive the host-only Runner environment file",
        )
        require(errors, "build" not in service, f"{name} must use a prebuilt digest-pinned image")
        image = str(service.get("image", ""))
        expected_env = {
            "spring-runner-ingress": "ELMOS_SPRING_INGRESS_IMAGE",
            "spring-runner-broker": "ELMOS_SPRING_WORKSPACE_SERVICE_IMAGE",
            "spring-runner-egress-proxy": "ELMOS_SPRING_EGRESS_PROXY_IMAGE",
        }[name]
        require(
            errors,
            re.fullmatch(
                rf"\$\{{{re.escape(expected_env)}:\?[^{{}}]+\}}", image
            )
            is not None,
            f"{name} image must be supplied by required {expected_env}",
        )
        require(
            errors,
            service.get("environment", {})
            == RUNNER_SERVICE_ENVIRONMENT_CONTRACT[name],
            f"{name} environment contract drift",
        )
        require(
            errors,
            service.get("tmpfs") == RUNNER_SERVICE_TMPFS_CONTRACT[name],
            f"{name} tmpfs contract drift",
        )
        for resource, expected in RUNNER_SERVICE_RESOURCE_CONTRACT[name].items():
            require(
                errors,
                service.get(resource) == expected,
                f"{name} {resource} contract drift",
            )
        require(
            errors,
            service.get("logging") == RUNNER_LOGGING_CONTRACT,
            f"{name} logging contract drift",
        )
        require(
            errors,
            service.get("healthcheck")
            == RUNNER_SERVICE_HEALTHCHECK_CONTRACT[name],
            f"{name} healthcheck contract drift",
        )
        for field in ("entrypoint", "command", "working_dir", "configs", "secrets"):
            require(
                errors,
                field not in service,
                f"{name} must inherit its digest-pinned image {field}",
            )
        raw_mounts = service.get("volumes", [])
        mounts = service_volumes(service)
        require(
            errors,
            isinstance(raw_mounts, list)
            and all(isinstance(item, dict) for item in raw_mounts)
            and len(raw_mounts) == len(mounts),
            f"{name} mounts must use parseable long-form bind records",
        )
        mounts_by_target = {
            str(mount.get("target")): mount
            for mount in mounts
            if isinstance(mount.get("target"), str)
        }
        expected_mounts = RUNNER_SERVICE_MOUNT_CONTRACT[name]
        require(
            errors,
            len(mounts) == len(mounts_by_target)
            and set(mounts_by_target) == set(expected_mounts),
            f"{name} mount inventory drift",
        )
        for target, (variable, read_write) in expected_mounts.items():
            mount = mounts_by_target.get(target)
            if mount is None:
                continue
            require(
                errors,
                mount.get("type") == "bind",
                f"{name} mount {target} must remain a bind mount",
            )
            require(
                errors,
                re.fullmatch(
                    rf"\$\{{{re.escape(variable)}:\?[^{{}}]+\}}",
                    str(mount.get("source", "")),
                )
                is not None,
                f"{name} mount {target} must use {variable}",
            )
            require(
                errors,
                mount.get("read_only") is (not read_write),
                f"{name} mount {target} access mode drift",
            )
            require(
                errors,
                mount.get("bind", {}).get("create_host_path") is False,
                f"{name} mount {target} must not auto-create its host source",
            )

    ingress = services.get("spring-runner-ingress", {})
    broker = services.get("spring-runner-broker", {})
    proxy = services.get("spring-runner-egress-proxy", {})
    require(errors, ingress.get("user") == "10004:10004", "HTTPS ingress must use its dedicated UID")
    require(
        errors,
        service_networks(ingress) == {"spring-runner-edge", "spring-runner-broker"},
        "HTTPS ingress may join only edge and broker networks",
    )
    require(
        errors,
        ingress.get("ports")
        == [
            {
                "target": 8443,
                "published": "${ELMOS_SPRING_RUNNER_HTTPS_PORT:?HTTPS port is required}",
                "host_ip": "${ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS:?private bind address is required}",
                "protocol": "tcp",
            }
        ],
        "HTTPS ingress must publish only its exact configured private 8443 binding",
    )
    require(errors, not broker.get("ports"), "Spring broker must not publish a host port")
    require(errors, not proxy.get("ports"), "egress proxy must not publish a host port")
    require(errors, broker.get("user") == "10001:10001", "Spring broker must use UID 10001")
    require(errors, proxy.get("user") == "10001:10001", "egress proxy must use UID 10001")
    require(errors, broker.get("group_add") == ["0"], "Spring broker needs only rootless socket group 0")
    require(
        errors,
        service_networks(broker) == {"spring-runner-broker", "spring-runner-control"},
        "Spring broker must not join edge or execution-egress networks",
    )
    require(
        errors,
        service_networks(proxy) == {"spring-runner-broker", "spring-runner-egress"},
        "allowlist proxy must be the only broker-to-egress bridge",
    )

    socket_mounts: list[str] = []
    for name, service in services.items():
        mount = volume_for_target(service, "/run/docker.sock")
        if mount:
            socket_mounts.append(name)
            require(errors, mount.get("read_only") is False, "broker Docker socket must be a deliberate read-write mount")
    require(errors, socket_mounts == ["spring-runner-broker"], "Docker socket must be confined to Spring broker")

    expected_secret_sources = {
        "/run/secrets/elmos-verifier-hmac": "ELMOS_SPRING_BROKER_VERIFIER_HMAC_SECRET_HOST_PATH",
        "/run/secrets/elmos-transformer-hmac": "ELMOS_SPRING_BROKER_TRANSFORMER_HMAC_SECRET_HOST_PATH",
        "/run/secrets/elmos-runtime-hmac": "ELMOS_SPRING_BROKER_RUNTIME_HMAC_SECRET_HOST_PATH",
    }
    for target, variable in expected_secret_sources.items():
        mount = volume_for_target(broker, target)
        require(errors, mount is not None, f"broker secret mount {target} is missing")
        if mount:
            require(errors, mount.get("read_only") is True, f"broker secret mount {target} must be read-only")
            require(
                errors,
                str(mount.get("source", "")).startswith("${" + variable + ":?"),
                f"broker secret {target} must use its security-domain copy",
            )
            require(
                errors,
                mount.get("bind", {}).get("create_host_path") is False,
                f"broker secret {target} must not be auto-created as a directory",
            )

    replay_target = "/var/lib/elmos/spring-auth-replay"
    replay_mount = volume_for_target(broker, replay_target)
    require(errors, replay_mount is not None, "Spring broker persistent replay mount is missing")
    if replay_mount:
        require(
            errors,
            str(replay_mount.get("source", "")).startswith(
                "${" + RUNNER_REPLAY_ENVIRONMENT + ":?"
            ),
            "Spring broker replay mount must use the required Runner host path",
        )
        require(
            errors,
            replay_mount.get("read_only") is False,
            "Spring broker replay mount must be read-write",
        )
        require(
            errors,
            replay_mount.get("bind", {}).get("create_host_path") is False,
            "Spring broker replay mount must fail closed instead of creating a host directory",
        )

    broker_environment = broker.get("environment", {})
    for name in (
        "ELMOS_WORKSPACE_DOCKER_ENABLED",
        "ELMOS_SPRING_RUNTIME_ENABLED",
        "ELMOS_EPHEMERAL_SPRING_VERIFIER_ENABLED",
        "ELMOS_EPHEMERAL_SPRING_TRANSFORMER_ENABLED",
    ):
        require(errors, broker_environment.get(name) == "true", f"broker must set {name}=true")
    expected_replay_roots = {
        "ELMOS_SPRING_RUNTIME_REPLAY_ROOT": replay_target + "/runtime",
        "ELMOS_SPRING_VERIFIER_REPLAY_ROOT": replay_target + "/verifier",
        "ELMOS_SPRING_TRANSFORMER_REPLAY_ROOT": replay_target + "/transformer",
    }
    for name, expected in expected_replay_roots.items():
        require(
            errors,
            broker_environment.get(name) == expected,
            f"broker must bind {name} to its persistent role-specific replay directory",
        )
    require(
        errors,
        broker_environment.get("ELMOS_JAVA_UPGRADE_INTERNAL_NETWORK") == "elmos-spring-runner-broker",
        "ephemeral Spring containers must use the internal broker network",
    )
    require(
        errors,
        broker_environment.get("ELMOS_JAVA_UPGRADE_EGRESS_PROXY_URL")
        == "http://spring-runner-egress-proxy:8080",
        "ephemeral transformer egress must use the allowlist proxy",
    )

    require(errors, isinstance(networks, dict), "runner Compose networks must be an object")
    if isinstance(networks, dict):
        require(
            errors,
            networks.get("spring-runner-edge", {}).get("internal") is True,
            "ingress edge network must be internal/default-deny",
        )
        require(
            errors,
            networks.get("spring-runner-broker", {}).get("internal") is True,
            "broker network must be internal/default-deny",
        )
        require(
            errors,
            networks.get("spring-runner-control", {}).get("external") is True,
            "database/control network must be externally pre-provisioned",
        )
        require(
            errors,
            re.fullmatch(
                r"\$\{ELMOS_SPRING_RUNNER_CONTROL_NETWORK:\?[^{}]+\}",
                str(networks.get("spring-runner-control", {}).get("name", "")),
            )
            is not None,
            "control network name must be explicitly supplied",
        )

    serialized = json.dumps(compose, sort_keys=True)
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID" not in serialized, "runner topology must not declare a single-tenant fallback")
    require(errors, ENGINE_SECRET_ENVIRONMENT not in serialized, "BFF-to-engine HMAC must never enter the Runner security domain")


def validate_application_compose(
    errors: list[str],
    compose: Mapping[str, Any],
    spring_overlay: Mapping[str, Any],
) -> None:
    services = compose.get("services", {})
    if not isinstance(services, dict):
        errors.append("application Compose services must be an object")
        return
    overlay_services = spring_overlay.get("services", {})
    if not isinstance(overlay_services, dict):
        errors.append("Spring application overlay services must be an object")
        return
    require(
        errors,
        set(overlay_services) == {"web-console", "java-engine-worker"},
        "Spring application overlay may modify only the BFF and Java worker",
    )
    web = services.get("web-console", {})
    worker = services.get("java-engine-worker", {})
    overlay_web = overlay_services.get("web-console", {})
    overlay_worker = overlay_services.get("java-engine-worker", {})
    web_environment = web.get("environment", {}) if isinstance(web, dict) else {}
    worker_environment = worker.get("environment", {}) if isinstance(worker, dict) else {}
    overlay_web_environment = (
        overlay_web.get("environment", {}) if isinstance(overlay_web, dict) else {}
    )
    require(
        errors,
        web_environment.get("ELMOS_SPRING_PROXY_MULTI_TENANT") == "true",
        "production Web Spring proxy must be multi-tenant",
    )
    require(
        errors,
        str(web_environment.get("ELMOS_SPRING_PROXY_ENABLED", "")).startswith(
            "${ELMOS_SPRING_PROXY_ENABLED:-false}"
        ),
        "production Web Spring proxy must remain opt-in",
    )
    require(
        errors,
        str(web_environment.get("ELMOS_SPRING_ENGINE_AUTH_ENABLED", "")).startswith(
            "${ELMOS_SPRING_ENGINE_AUTH_ENABLED:-false}"
        ),
        "baseline Web engine authentication must default disabled",
    )
    for name in (
        "ELMOS_SPRING_PROXY_ENABLED",
        "ELMOS_SPRING_PROXY_MULTI_TENANT",
        "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    ):
        require(
            errors,
            overlay_web_environment.get(name) == "true",
            f"Spring application overlay must set {name}=true",
        )
    require(
        errors,
        worker.get("profiles") == ["spring"],
        "application Spring worker must remain profile-gated",
    )
    require(
        errors,
        worker.get("env_file") == [],
        "application Spring worker must not receive the broad application env_file",
    )
    for name in WORKER_PATH_OVERRIDE_ENVIRONMENTS:
        require(
            errors,
            worker_environment.get(name) == "",
            f"application Spring worker must clear dangerous path override {name}",
        )
    require(
        errors,
        overlay_web.get("depends_on", {}).get("java-engine-worker", {}).get(
            "condition"
        )
        == "service_started",
        "Spring overlay Web must depend on the profile-gated Java worker",
    )
    serialized = json.dumps(
        {"application": compose, "spring_overlay": spring_overlay}, sort_keys=True
    )
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID" not in serialized, "production Compose must not declare a single-tenant identity")
    require(errors, worker.get("user") == "10001:10001", "application Spring worker must use UID 10001")
    require(errors, worker.get("read_only") is True, "application Spring worker root must be read-only")
    require(errors, volume_for_target(worker, "/run/docker.sock") is None, "application Spring worker must never receive a Docker socket")
    engine_target = "/run/secrets/elmos-spring-engine-hmac"
    require(
        errors,
        volume_for_target(web, engine_target) is None,
        "non-Spring baseline Web must not require the engine HMAC file",
    )
    require(
        errors,
        volume_for_target(worker, engine_target) is None,
        "engine HMAC must be activated through the Spring application overlay",
    )
    web_engine = volume_for_target(overlay_web, engine_target)
    worker_engine = volume_for_target(overlay_worker, engine_target)
    require(
        errors,
        web_engine is not None and worker_engine is not None,
        "Spring overlay must give the application BFF and worker the engine HMAC",
    )
    if web_engine and worker_engine:
        web_source = str(web_engine.get("source", ""))
        worker_source = str(worker_engine.get("source", ""))
        require(
            errors,
            web_source.startswith("${" + ENGINE_SECRET_ENVIRONMENT + ":?"),
            "BFF engine HMAC must require the application-host path",
        )
        require(errors, web_source == worker_source, "BFF and worker engine HMAC mounts must use the same application-host copy")
        require(errors, web_engine.get("read_only") is True and worker_engine.get("read_only") is True, "engine HMAC mounts must be read-only")
        require(
            errors,
            web_engine.get("bind", {}).get("create_host_path") is False
            and worker_engine.get("bind", {}).get("create_host_path") is False,
            "engine HMAC mounts must fail closed instead of creating directories",
        )
    replay_target = "/var/lib/elmos/spring-engine-auth-replay"
    require(
        errors,
        worker_environment.get("ELMOS_SPRING_ENGINE_AUTH_REPLAY_ROOT") == replay_target,
        "application worker must use the persistent engine replay mount",
    )
    require(
        errors,
        volume_for_target(web, replay_target) is None
        and volume_for_target(worker, replay_target) is None,
        "baseline application services must not receive the Spring replay host directory",
    )
    worker_replay = volume_for_target(overlay_worker, replay_target)
    require(
        errors,
        worker_replay is not None,
        "Spring overlay must mount persistent engine replay state",
    )
    if worker_replay:
        require(
            errors,
            str(worker_replay.get("source", "")).startswith(
                "${" + ENGINE_REPLAY_ENVIRONMENT + ":?"
            ),
            "Spring engine replay mount must use the required application-host path",
        )
        require(
            errors,
            worker_replay.get("read_only") is False,
            "Spring engine replay mount must be read-write",
        )
        require(
            errors,
            worker_replay.get("bind", {}).get("create_host_path") is False,
            "Spring engine replay mount must fail closed instead of creating a host directory",
        )
    for variable in (
        "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
        "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
        "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    ):
        require(
            errors,
            str(worker_environment.get(variable, "")).startswith("${" + variable + ":-https://"),
            f"{variable} must fail closed to an HTTPS-only invalid endpoint",
        )
    expected_sources = {
        "/run/secrets/elmos-verifier-hmac": "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
        "/run/secrets/elmos-transformer-hmac": "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
        "/run/secrets/elmos-runtime-hmac": "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
    }
    for target, variable in expected_sources.items():
        mount = volume_for_target(worker, target)
        require(errors, mount is not None, f"application worker secret {target} is missing")
        if mount:
            require(errors, mount.get("read_only") is True, f"application worker secret {target} must be read-only")
            require(
                errors,
                variable in str(mount.get("source", "")),
                f"application worker secret {target} must use the application-host copy",
            )


def validate_ingress(errors: list[str], config: str) -> None:
    require(
        errors,
        hashlib.sha256(config.encode("utf-8")).hexdigest()
        == EXPECTED_INGRESS_CONFIG_SHA256,
        "Spring ingress configuration must remain byte-for-byte equal to the reviewed allowlist",
    )
    require(errors, "listen 8443 ssl;" in config, "Spring ingress must terminate TLS")
    require(errors, "ssl_protocols TLSv1.2 TLSv1.3;" in config, "Spring ingress TLS floor drift")
    require(errors, "ssl_session_tickets off;" in config, "Spring ingress must disable TLS session tickets")
    require(errors, "location /" in config and "return 404;" in config, "Spring ingress must deny all undeclared routes")
    require(
        errors,
        "client_max_body_size 1k;" in config,
        "Spring ingress default request-body limit must remain 1k",
    )
    for path in BROKER_PATHS:
        require(errors, f"location = {path}" in config, f"Spring ingress lacks exact route {path}")
        location = re.search(
            rf"location = {re.escape(path)} \{{(?P<body>.*?)\n    \}}",
            config,
            flags=re.DOTALL,
        )
        expected_limit = BROKER_BODY_LIMITS[path]
        require(
            errors,
            location is not None
            and f"client_max_body_size {expected_limit};" in location.group("body"),
            f"Spring ingress {path} request-body limit must remain {expected_limit}",
        )
    require(errors, config.count("limit_except POST { deny all; }") == 3, "Spring ingress routes must accept POST only")
    require(errors, config.count("proxy_pass http://spring-runner-broker:8082;") == 3, "Spring ingress must proxy only to the private broker")
    for family in ("Transformer", "Verifier", "Runtime"):
        for field in ("Timestamp", "Nonce", "Signature"):
            require(errors, f"X-ELMOS-{family}-{field}" in config, f"Spring ingress must preserve {family} {field} HMAC header")


def validate_documentation(errors: list[str], paths: ContractPaths) -> None:
    environment = paths.environment_example.read_text(encoding="utf-8")
    spring_launch = paths.spring_launch_environment_example.read_text(encoding="utf-8")
    rootless = paths.rootless_readme.read_text(encoding="utf-8")
    production = paths.production_readme.read_text(encoding="utf-8")
    runner_environment = paths.runner_environment_example.read_text(encoding="utf-8")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in environment, "production env must not contain a single-tenant identity")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in spring_launch, "spring launch env must not contain a single-tenant identity")
    for variable in APPLICATION_SECRET_ENVIRONMENTS + (
        ENGINE_SECRET_ENVIRONMENT,
        ENGINE_REPLAY_ENVIRONMENT,
    ):
        require(errors, f"{variable}=" in spring_launch, f"spring launch env example lacks {variable}")
    require(
        errors,
        "共享的只读文件应为 `0444`" not in rootless,
        "rootless HMAC guidance must not prescribe world-readable secrets",
    )
    require(errors, "LOCAL_NON_CERTIFYING" in rootless, "local rootless override must be labeled non-certifying")
    require(errors, "docker-compose.spring-runner.yml" in production, "production runbook must reference the dedicated Runner Compose")
    require(
        errors,
        "docker-compose.spring-application.yml" in production,
        "production runbook must require the Spring application overlay",
    )
    require(
        errors,
        "EXTERNAL_EVIDENCE_INTAKE=NOT_RUN" in production,
        "production runbook must retain external evidence intake as NOT_RUN",
    )
    for token in (
        "sudo uv run --quiet --with pyyaml",
        '--rootless-owner-uid "$RUNNER_UID"',
        '--rootless-owner-gid "$RUNNER_GID"',
        "Docker daemon\n# 仍必须是 rootless",
    ):
        require(
            errors,
            token in production,
            f"production runbook lacks controlled root observer contract: {token}",
        )
    runner_keys = {
        line.split("=", 1)[0]
        for line in runner_environment.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    require(errors, runner_keys == RUNNER_ENVIRONMENT_ALLOWLIST, "Runner env example key inventory must equal the strict allowlist")
    require(errors, ENGINE_SECRET_ENVIRONMENT not in runner_environment, "Runner env example must exclude the BFF-to-engine HMAC")
    assignments = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in spring_launch.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    application_paths = [
        assignments.get(name, "")
        for name in (ENGINE_SECRET_ENVIRONMENT,) + APPLICATION_SECRET_ENVIRONMENTS
    ]
    require(
        errors,
        all(application_paths) and len(set(application_paths)) == 4,
        "the four application-domain Spring HMAC paths must be non-empty and distinct",
    )
    runner_assignments = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in runner_environment.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    require(
        errors,
        bool(assignments.get(ENGINE_REPLAY_ENVIRONMENT))
        and bool(runner_assignments.get(RUNNER_REPLAY_ENVIRONMENT))
        and assignments[ENGINE_REPLAY_ENVIRONMENT]
        != runner_assignments[RUNNER_REPLAY_ENVIRONMENT],
        "application and Runner replay host directories must remain independently configured",
    )
    runner_only_keys = RUNNER_ENVIRONMENT_ALLOWLIST - {
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
    }
    app_assignments = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in environment.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    leaked_runner_keys = sorted(runner_only_keys & app_assignments.keys())
    require(
        errors,
        not leaked_runner_keys,
        "application env example must exclude Runner-only keys: "
        + ", ".join(leaked_runner_keys),
    )


def validate_static(paths: ContractPaths | None = None) -> list[str]:
    paths = paths or ContractPaths()
    errors: list[str] = []
    try:
        runner = read_yaml(paths.runner_compose)
        application = read_yaml(paths.application_compose)
        application_spring_overlay = read_yaml(paths.application_spring_overlay)
        ingress = paths.ingress_config.read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        return [f"static contract could not be loaded: {error}"]
    validate_runner_compose(errors, runner)
    validate_application_compose(errors, application, application_spring_overlay)
    validate_ingress(errors, ingress)
    try:
        validate_documentation(errors, paths)
    except OSError as error:
        errors.append(f"documentation contract could not be loaded: {error}")
    return errors


def environment_path(name: str, environment: Mapping[str, str]) -> Path:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{name} must be absolute")
    if path != Path(os.path.normpath(path)):
        raise ValueError(f"{name} must be normalized")
    return path


def environment_integer(name: str, environment: Mapping[str, str]) -> int:
    value = environment.get(name, "").strip()
    if not value.isdigit():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def private_https_endpoint(
    environment: Mapping[str, str],
) -> tuple[str, int]:
    """Return a canonical private unicast bind address and valid TCP port."""

    raw_address = environment.get("ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS", "").strip()
    try:
        address = ipaddress.ip_address(raw_address)
    except ValueError as error:
        raise ValueError(
            "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS must be a canonical private unicast IP"
        ) from error
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("::1/128"),
    )
    if str(address) != raw_address or not any(
        address.version == network.version and address in network
        for network in private_networks
    ):
        raise ValueError(
            "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS must be a canonical private unicast IP"
        )
    raw_port = environment.get("ELMOS_SPRING_RUNNER_HTTPS_PORT", "").strip()
    if not raw_port.isdigit() or str(int(raw_port)) != raw_port:
        raise ValueError("ELMOS_SPRING_RUNNER_HTTPS_PORT must be an integer from 1 to 65535")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ValueError("ELMOS_SPRING_RUNNER_HTTPS_PORT must be an integer from 1 to 65535")
    return str(address), port


def paths_overlap(left: Path, right: Path) -> bool:
    """Compare lexical, canonical, and existing filesystem object identities."""

    lexical_overlap = (
        left == right
        or left.is_relative_to(right)
        or right.is_relative_to(left)
    )
    if lexical_overlap:
        return True
    try:
        resolved_left = left.resolve(strict=True)
        resolved_right = right.resolve(strict=True)
        if (
            resolved_left == resolved_right
            or resolved_left.is_relative_to(resolved_right)
            or resolved_right.is_relative_to(resolved_left)
        ):
            return True
    except OSError:
        pass
    try:
        left_details = left.stat()
        right_details = right.stat()
    except OSError:
        return False
    return (left_details.st_dev, left_details.st_ino) == (
        right_details.st_dev,
        right_details.st_ino,
    )


def validate_sensitive_path_isolation(
    errors: list[str],
    sensitive_paths: Mapping[str, Path],
    operational_roots: Mapping[str, Path],
) -> None:
    """Keep credentials and secret roots outside every mutable runtime tree."""

    for sensitive_name, sensitive_path in sensitive_paths.items():
        for root_name, root_path in operational_roots.items():
            require(
                errors,
                not paths_overlap(sensitive_path, root_path),
                f"{sensitive_name} must not equal, contain, or be contained by {root_name}",
            )


def validate_operational_root_isolation(
    errors: list[str], operational_roots: Mapping[str, Path]
) -> None:
    """Keep every RO/RW Runner data role on an independent host tree/inode."""

    ordered = sorted(operational_roots.items())
    for index, (left_name, left_path) in enumerate(ordered):
        for right_name, right_path in ordered[index + 1 :]:
            require(
                errors,
                not paths_overlap(left_path, right_path),
                f"{left_name} must not equal, contain, be contained by, or alias {right_name}",
            )


def stable_directory_identity(details: os.stat_result) -> tuple[int, ...]:
    """Identity/security fields unaffected by normal child-file activity."""

    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
    )


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


def safe_ancestor_metadata(
    path: Path,
    *,
    allowed_uids: set[int],
    label: str,
) -> tuple[list[tuple[Path, tuple[int, ...]]], str | None]:
    """Capture a no-symlink ancestor chain that untrusted owners cannot replace."""

    metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            details = parent.lstat()
            if not stat.S_ISDIR(details.st_mode) or stat.S_ISLNK(details.st_mode):
                return [], f"{label} must not traverse symbolic-link parent or non-directory ancestors"
            writable_without_sticky = bool(stat.S_IMODE(details.st_mode) & 0o022) and not bool(
                details.st_mode & stat.S_ISVTX
            )
            if writable_without_sticky:
                return [], f"{label} must not traverse group/other-writable non-sticky ancestors"
            if details.st_uid not in allowed_uids:
                return [], f"{label} must not traverse foreign-owned ancestors"
            metadata.append((parent, stable_directory_identity(details)))
    except OSError:
        return [], f"{label} has a missing or unreadable ancestor"
    return metadata, None


def ancestors_remain_stable(
    metadata: Sequence[tuple[Path, tuple[int, ...]]],
) -> bool:
    try:
        return all(
            not stat.S_ISLNK((current := parent.lstat()).st_mode)
            and stable_directory_identity(current) == expected
            for parent, expected in metadata
        )
    except OSError:
        return False


def owner_only_file(
    errors: list[str],
    path: Path,
    *,
    label: str,
    expected_uid: int,
    expected_gid: int,
    minimum_size: int = 1,
    maximum_size: int = 4096,
    canonical_hmac_secret: bool = False,
    inspect_contents: bool = True,
    expected_parent_uid: int | None = None,
    expected_parent_gid: int | None = None,
) -> tuple[int, int, str | None] | None:
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return None
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids={
            0,
            os.getuid(),
            expected_uid,
            *(set() if expected_parent_uid is None else {expected_parent_uid}),
        },
        label=label,
    )
    if ancestor_error is not None:
        errors.append(ancestor_error)
        return None
    try:
        details = path.lstat()
        parent_details = path.parent.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append(f"{label} is missing")
        return None
    parent_uid_valid = (
        parent_details.st_uid in {0, os.getuid(), expected_uid}
        if expected_parent_uid is None
        else parent_details.st_uid == expected_parent_uid
    )
    parent_gid_valid = (
        parent_details.st_gid in {0, os.getgid(), expected_gid}
        if expected_parent_gid is None
        else parent_details.st_gid == expected_parent_gid
    )
    if (
        stat.S_IMODE(parent_details.st_mode) != 0o700
        or not parent_uid_valid
        or not parent_gid_valid
    ):
        errors.append(
            f"{label} immediate parent must be a trusted 0700 directory"
        )
        return None
    valid = True
    for condition, message in (
        (not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository"),
        (stat.S_ISREG(details.st_mode) and not stat.S_ISLNK(details.st_mode), f"{label} must be a regular non-symlink file"),
        (details.st_nlink == 1, f"{label} must not be hard-linked"),
        (stat.S_IMODE(details.st_mode) in {0o400, 0o600}, f"{label} mode must be 0400 or 0600"),
        (details.st_uid == expected_uid, f"{label} owner UID must equal {expected_uid}"),
        (details.st_gid == expected_gid, f"{label} owner GID must equal {expected_gid}"),
        (minimum_size <= details.st_size <= maximum_size, f"{label} size must be {minimum_size}-{maximum_size} bytes"),
    ):
        if not condition:
            errors.append(message)
            valid = False
    if not valid:
        return None
    if not inspect_contents and not hasattr(os, "O_PATH"):
        errors.append(f"{label} metadata-only validation requires Linux O_PATH")
        return None
    flags = getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_RDONLY if inspect_contents else os.O_PATH
    try:
        descriptor = os.open(path, flags)
    except OSError:
        errors.append(f"{label} could not be opened without following links")
        return None
    try:
        opened = os.fstat(descriptor)
        if stable_file_metadata(opened) != stable_file_metadata(details):
            errors.append(f"{label} changed while it was being validated")
            return None
        contents: bytes | None = None
        if inspect_contents:
            chunks: list[bytes] = []
            remaining = maximum_size + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            contents = b"".join(chunks)
        after = os.fstat(descriptor)
        after_path = path.lstat()
        ancestors_unchanged = ancestors_remain_stable(ancestor_metadata)
        if (
            stable_file_metadata(after) != stable_file_metadata(opened)
            or stable_file_metadata(after_path) != stable_file_metadata(opened)
            or (contents is not None and len(contents) != opened.st_size)
            or not ancestors_unchanged
        ):
            errors.append(f"{label} or parent path changed while it was being read")
            return None
        if canonical_hmac_secret:
            if contents is None:
                errors.append(f"{label} canonical HMAC bytes were not inspected")
                return None
            try:
                decoded = contents.decode("utf-8", errors="strict")
            except UnicodeError:
                errors.append(f"{label} must contain canonical UTF-8 HMAC bytes")
                return None
            if (
                not decoded
                or boundary_whitespace(ord(decoded[0]))
                or boundary_whitespace(ord(decoded[-1]))
            ):
                errors.append(
                    f"{label} must not have leading or trailing HMAC whitespace"
                )
                return None
        digest = hashlib.sha256(contents).hexdigest() if contents is not None else None
        return (opened.st_dev, opened.st_ino, digest)
    except OSError:
        errors.append(f"{label} changed or became unreadable while it was being read")
        return None
    finally:
        os.close(descriptor)


def trusted_regular_file(
    errors: list[str],
    path: Path,
    *,
    label: str,
    expected_uid: int,
    expected_gid: int,
    expected_parent_uid: int,
    expected_parent_gid: int,
    minimum_size: int = 1,
    maximum_size: int = 1024 * 1024,
    expected_sha256: str | None = None,
) -> tuple[int, int, str | None] | None:
    """Validate a bind-mounted regular file and optionally read reviewed bytes."""

    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return None
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids={0, os.getuid(), expected_uid, expected_parent_uid},
        label=label,
    )
    if ancestor_error is not None:
        errors.append(ancestor_error)
        return None
    try:
        details = path.lstat()
        parent_details = path.parent.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append(f"{label} is missing")
        return None
    valid = True
    for condition, message in (
        (not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository"),
        (
            stat.S_ISDIR(parent_details.st_mode)
            and not stat.S_ISLNK(parent_details.st_mode)
            and stat.S_IMODE(parent_details.st_mode) == 0o700,
            f"{label} immediate parent must be a non-symlink 0700 directory",
        ),
        (
            parent_details.st_uid == expected_parent_uid
            and parent_details.st_gid == expected_parent_gid,
            f"{label} immediate parent owner UID/GID must equal {expected_parent_uid}:{expected_parent_gid}",
        ),
        (
            stat.S_ISREG(details.st_mode) and not stat.S_ISLNK(details.st_mode),
            f"{label} must be a regular non-symlink file",
        ),
        (details.st_nlink == 1, f"{label} must not be hard-linked"),
        (
            stat.S_IMODE(details.st_mode) & 0o022 == 0,
            f"{label} must not be group/other-writable",
        ),
        (details.st_uid == expected_uid, f"{label} owner UID must equal {expected_uid}"),
        (details.st_gid == expected_gid, f"{label} owner GID must equal {expected_gid}"),
        (
            minimum_size <= details.st_size <= maximum_size,
            f"{label} size must be {minimum_size}-{maximum_size} bytes",
        ),
    ):
        if not condition:
            errors.append(message)
            valid = False
    if not valid:
        return None

    flags = getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_RDONLY if expected_sha256 is not None else getattr(os, "O_PATH", os.O_RDONLY)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        errors.append(f"{label} could not be opened without following links")
        return None
    try:
        opened = os.fstat(descriptor)
        if stable_file_metadata(opened) != stable_file_metadata(details):
            errors.append(f"{label} changed while it was being validated")
            return None
        digest: str | None = None
        if expected_sha256 is not None:
            chunks: list[bytes] = []
            remaining = maximum_size + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            contents = b"".join(chunks)
            if len(contents) != opened.st_size:
                errors.append(f"{label} changed while its reviewed bytes were read")
                return None
            digest = hashlib.sha256(contents).hexdigest()
            if digest != expected_sha256:
                errors.append(f"{label} must match the reviewed repository digest")
                return None
        after = os.fstat(descriptor)
        after_path = path.lstat()
        if (
            stable_file_metadata(after) != stable_file_metadata(opened)
            or stable_file_metadata(after_path) != stable_file_metadata(opened)
            or not ancestors_remain_stable(ancestor_metadata)
        ):
            errors.append(f"{label} or parent path changed while it was being validated")
            return None
        return (opened.st_dev, opened.st_ino, digest)
    except OSError:
        errors.append(f"{label} changed or became unreadable while it was being validated")
        return None
    finally:
        os.close(descriptor)


def trusted_unix_socket(
    errors: list[str],
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    """Validate the rootless Docker endpoint without following replaceable paths."""

    label = "rootless Docker socket"
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids={0, os.getuid(), expected_uid},
        label=label,
    )
    if ancestor_error is not None:
        errors.append(ancestor_error)
        return
    try:
        details = path.lstat()
        parent_details = path.parent.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append(f"{label} is missing")
        return
    require(errors, not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository")
    require(
        errors,
        stat.S_ISDIR(parent_details.st_mode)
        and not stat.S_ISLNK(parent_details.st_mode)
        and stat.S_IMODE(parent_details.st_mode) == 0o700
        and parent_details.st_uid == expected_uid
        and parent_details.st_gid == expected_gid,
        f"{label} immediate parent must be a trusted 0700 UID/GID {expected_uid}:{expected_gid} directory",
    )
    require(
        errors,
        stat.S_ISSOCK(details.st_mode) and not stat.S_ISLNK(details.st_mode),
        f"{label} must be a Unix socket",
    )
    require(errors, details.st_uid == expected_uid, f"{label} owner mismatch")
    require(errors, details.st_gid == expected_gid, f"{label} group mismatch")
    require(errors, details.st_mode & 0o007 == 0, f"{label} must not grant other permissions")
    try:
        after = path.lstat()
    except OSError:
        errors.append(f"{label} changed while it was being validated")
        return
    require(
        errors,
        stable_file_metadata(details) == stable_file_metadata(after)
        and ancestors_remain_stable(ancestor_metadata),
        f"{label} or an ancestor changed while it was being validated",
    )


def protected_directory(
    errors: list[str],
    path: Path,
    *,
    label: str,
    expected_uid: int,
    expected_gid: int,
    allowed_ancestor_uids: set[int] | None = None,
) -> None:
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids=(
            {0, os.getuid(), expected_uid}
            if allowed_ancestor_uids is None
            else set(allowed_ancestor_uids) | {0, os.getuid(), expected_uid}
        ),
        label=label,
    )
    if ancestor_error is not None:
        errors.append(ancestor_error)
        return
    try:
        details = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError:
        errors.append(f"{label} is missing")
        return
    require(errors, not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository")
    require(errors, stat.S_ISDIR(details.st_mode) and not stat.S_ISLNK(details.st_mode), f"{label} must be a non-symlink directory")
    require(errors, stat.S_IMODE(details.st_mode) == 0o700, f"{label} mode must equal 0700")
    require(errors, details.st_uid == expected_uid, f"{label} owner UID must equal {expected_uid}")
    require(errors, details.st_gid == expected_gid, f"{label} owner GID must equal {expected_gid}")
    require(
        errors,
        stable_directory_identity(details) == stable_directory_identity(after)
        and ancestors_remain_stable(ancestor_metadata),
        f"{label} or an ancestor changed while it was being validated",
    )


def ordinary_directory(
    errors: list[str],
    path: Path,
    *,
    label: str,
    allowed_uids: set[int] | None = None,
    allowed_gids: set[int] | None = None,
) -> None:
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return
    trusted_uids = {0, os.getuid()} if allowed_uids is None else set(allowed_uids)
    trusted_gids = {0, os.getgid()} if allowed_gids is None else set(allowed_gids)
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids=trusted_uids,
        label=label,
    )
    if ancestor_error is not None:
        errors.append(ancestor_error)
        return
    try:
        details = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError:
        errors.append(f"{label} is missing")
        return
    require(errors, not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository")
    require(errors, stat.S_ISDIR(details.st_mode) and not stat.S_ISLNK(details.st_mode), f"{label} must be a non-symlink directory")
    require(errors, stat.S_IMODE(details.st_mode) & 0o022 == 0, f"{label} must not be group/other-writable")
    require(errors, details.st_uid in trusted_uids, f"{label} owner UID is outside the trusted set")
    require(errors, details.st_gid in trusted_gids, f"{label} owner GID is outside the trusted set")
    require(
        errors,
        stable_directory_identity(details) == stable_directory_identity(after)
        and ancestors_remain_stable(ancestor_metadata),
        f"{label} or an ancestor changed while it was being validated",
    )


def command_json(command: Sequence[str]) -> Any:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "command failed"
        raise RuntimeError(f"{command[0]} inspection failed: {detail}")
    return json.loads(completed.stdout)


def docker_command(socket_path: Path, *arguments: str) -> list[str]:
    return ["docker", "--host", f"unix://{socket_path}", *arguments]


def stable_file_metadata(details: os.stat_result) -> tuple[int, ...]:
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


def secure_environment_file_bytes(
    path: Path,
    *,
    expected_owner_uid: int | None = None,
    expected_owner_gid: int | None = None,
) -> tuple[bytes | None, os.stat_result | None, os.stat_result | None, list[str]]:
    """Read an owner-only file without following links or accepting path races."""

    errors: list[str] = []
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        return None, None, None, [
            "Runner environment file path must be normalized, absolute, and non-root"
        ]

    owner_uid = os.getuid() if expected_owner_uid is None else expected_owner_uid
    owner_gid = os.getgid() if expected_owner_gid is None else expected_owner_gid
    ancestor_metadata, ancestor_error = safe_ancestor_metadata(
        path,
        allowed_uids={0, os.getuid(), owner_uid},
        label="Runner environment file",
    )
    if ancestor_error is not None:
        return None, None, None, [ancestor_error]
    try:
        details = path.lstat()
        initial_parent_details = path.parent.lstat()
    except OSError:
        return None, None, None, ["Runner environment file is missing or unreadable"]

    if stat.S_ISLNK(details.st_mode):
        return None, None, None, ["Runner environment file must not be a symbolic link"]
    if not stat.S_ISREG(details.st_mode):
        return None, None, None, ["Runner environment file must be a regular file"]
    if details.st_nlink != 1:
        return None, None, None, ["Runner environment file must not be hard-linked"]
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None, None, None, ["Runner environment file is missing or unreadable"]
    if resolved.is_relative_to(ROOT.resolve()):
        return None, None, None, ["Runner environment file must be outside the repository"]
    if (
        stat.S_IMODE(initial_parent_details.st_mode) != 0o700
        or initial_parent_details.st_uid != owner_uid
        or initial_parent_details.st_gid != owner_gid
    ):
        return None, None, None, [
            f"Runner environment parent must be mode 0700 and owned by UID/GID {owner_uid}:{owner_gid}"
        ]

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None, None, None, [
            "Runner environment file is missing, unreadable, or not a regular non-symlink file"
        ]

    raw = b""
    opened_details: os.stat_result | None = None
    parent_details: os.stat_result | None = None
    try:
        opened_details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_details.st_mode)
            or stable_file_metadata(opened_details) != stable_file_metadata(details)
            or opened_details.st_nlink != 1
        ):
            return None, None, None, [
                "Runner environment file changed while it was being validated"
            ]
        mode = stat.S_IMODE(opened_details.st_mode)
        if mode not in {0o400, 0o600}:
            errors.append("Runner environment file mode must be 0400 or 0600")
        if opened_details.st_uid != owner_uid or opened_details.st_gid != owner_gid:
            errors.append(
                f"Runner environment file must be owned by UID/GID {owner_uid}:{owner_gid}"
            )
        if opened_details.st_size > 65536:
            return None, None, None, errors + [
                "Runner environment file must not exceed 65536 bytes"
            ]

        chunks: list[bytes] = []
        remaining = 65537
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after_read_details = os.fstat(descriptor)
        after_read_path_details = path.lstat()
        ancestors_unchanged = ancestors_remain_stable(ancestor_metadata)
        if (
            stable_file_metadata(after_read_details) != stable_file_metadata(opened_details)
            or stable_file_metadata(after_read_path_details) != stable_file_metadata(opened_details)
            or len(raw) != opened_details.st_size
            or not ancestors_unchanged
        ):
            return None, None, None, errors + [
                "Runner environment file or parent path changed while it was being read"
            ]
        parent_details = path.parent.lstat()
    except OSError:
        return None, None, None, errors + [
            "Runner environment file changed or became unreadable while it was being read"
        ]
    finally:
        os.close(descriptor)

    if len(raw) > 65536:
        return None, None, None, errors + [
            "Runner environment file must not exceed 65536 bytes"
        ]
    return raw, opened_details, parent_details, errors


def load_environment_file(
    path: Path,
    process_environment: Mapping[str, str] | None = None,
    *,
    expected_owner_uid: int | None = None,
    expected_owner_gid: int | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Parse a Runner env file as inert data and apply allowlisted overrides."""

    errors: list[str] = []
    process_environment = process_environment if process_environment is not None else os.environ
    raw, details, parent_details, read_errors = secure_environment_file_bytes(
        path,
        expected_owner_uid=expected_owner_uid,
        expected_owner_gid=expected_owner_gid,
    )
    errors.extend(read_errors)
    if raw is None or details is None or parent_details is None:
        return {}, errors
    resolved = path
    require(errors, stat.S_IMODE(parent_details.st_mode) == 0o700, "Runner environment parent mode must equal 0700")
    values: dict[str, str] = {}
    try:
        content = raw.decode("utf-8")
    except UnicodeError:
        return {}, errors + ["Runner environment file must be valid UTF-8"]
    for number, raw_line in enumerate(content.splitlines(), start=1):
        if len(raw_line) > 8192:
            errors.append(f"Runner environment line {number} exceeds 8192 characters")
            continue
        if not raw_line or raw_line.startswith("#"):
            continue
        if raw_line != raw_line.strip() or "=" not in raw_line:
            errors.append(f"Runner environment line {number} must be exact NAME=value data")
            continue
        name, value = raw_line.split("=", 1)
        if not ENVIRONMENT_NAME.fullmatch(name):
            errors.append(f"Runner environment line {number} has an invalid name")
            continue
        if name not in RUNNER_ENVIRONMENT_ALLOWLIST:
            errors.append(f"Runner environment line {number} uses unknown variable {name}")
            continue
        if name in values:
            errors.append(f"Runner environment line {number} duplicates {name}")
            continue
        if not value or not ENVIRONMENT_VALUE.fullmatch(value):
            errors.append(f"Runner environment line {number} has an unsafe or empty value for {name}")
            continue
        values[name] = value

    for name in RUNNER_ENVIRONMENT_ALLOWLIST:
        if name not in process_environment:
            continue
        value = process_environment[name]
        if not value or not ENVIRONMENT_VALUE.fullmatch(value):
            errors.append(f"process override has an unsafe or empty value for {name}")
            continue
        values[name] = value

    configured_path = values.get("ELMOS_SPRING_RUNNER_ENV_FILE")
    if configured_path and Path(configured_path) != resolved:
        errors.append("ELMOS_SPRING_RUNNER_ENV_FILE must identify the parsed environment file")
    values["ELMOS_SPRING_RUNNER_ENV_FILE"] = str(resolved)

    try:
        rootless_uid = environment_integer("ELMOS_ROOTLESS_UID", values)
        rootless_gid = environment_integer("ELMOS_ROOTLESS_GID", values)
        require(errors, details.st_uid == rootless_uid, "Runner environment file owner UID must equal ELMOS_ROOTLESS_UID")
        require(errors, details.st_gid == rootless_gid, "Runner environment file owner GID must equal ELMOS_ROOTLESS_GID")
        if "parent_details" in locals():
            require(errors, parent_details.st_uid == rootless_uid, "Runner environment parent owner UID must equal ELMOS_ROOTLESS_UID")
            require(errors, parent_details.st_gid == rootless_gid, "Runner environment parent owner GID must equal ELMOS_ROOTLESS_GID")
    except ValueError as error:
        errors.append(str(error))

    missing = sorted(RUNNER_ENVIRONMENT_ALLOWLIST - values.keys())
    if missing:
        errors.append("Runner environment is missing allowlisted variables: " + ", ".join(missing))
    return values, errors


def validate_host(
    paths: ContractPaths | None = None,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    paths = paths or ContractPaths()
    errors = validate_static(paths)
    environment = environment if environment is not None else os.environ
    try:
        rootless_uid = environment_integer("ELMOS_ROOTLESS_UID", environment)
        rootless_gid = environment_integer("ELMOS_ROOTLESS_GID", environment)
        broker_uid = environment_integer("ELMOS_SPRING_BROKER_SECRET_MAPPED_UID", environment)
        broker_gid = environment_integer("ELMOS_SPRING_BROKER_SECRET_MAPPED_GID", environment)
        ingress_uid = environment_integer("ELMOS_SPRING_INGRESS_SECRET_MAPPED_UID", environment)
        ingress_gid = environment_integer("ELMOS_SPRING_INGRESS_SECRET_MAPPED_GID", environment)
        socket_path = environment_path("ELMOS_ROOTLESS_DOCKER_SOCKET", environment)
        secret_root = environment_path("ELMOS_SPRING_BROKER_SECRET_ROOT", environment)
        tls_root = environment_path("ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT", environment)
        replay_root = environment_path(RUNNER_REPLAY_ENVIRONMENT, environment)
    except ValueError as error:
        errors.append(str(error))
        return errors

    try:
        runner_compose = read_yaml(paths.runner_compose)
        validate_resolved_network_isolation(errors, runner_compose, environment)
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        errors.append(f"Runner network isolation contract could not be loaded: {error}")

    protected_directory(
        errors,
        secret_root,
        label="broker secret root",
        expected_uid=rootless_uid,
        expected_gid=rootless_gid,
        allowed_ancestor_uids={rootless_uid},
    )
    protected_directory(
        errors,
        tls_root,
        label="ingress TLS secret root",
        expected_uid=rootless_uid,
        expected_gid=rootless_gid,
        allowed_ancestor_uids={rootless_uid},
    )
    protected_directory(
        errors,
        replay_root,
        label="Spring Runner replay root",
        expected_uid=broker_uid,
        expected_gid=broker_gid,
        allowed_ancestor_uids={rootless_uid, broker_uid},
    )
    require(
        errors,
        replay_root not in {secret_root, tls_root}
        and not replay_root.is_relative_to(secret_root)
        and not replay_root.is_relative_to(tls_root),
        "Spring Runner replay root must be isolated from secret roots",
    )
    try:
        private_https_endpoint(environment)
    except ValueError as error:
        errors.append(str(error))

    operational_roots: dict[str, Path] = {RUNNER_REPLAY_ENVIRONMENT: replay_root}
    for name in OPERATIONAL_ROOT_ENVIRONMENTS:
        if name == RUNNER_REPLAY_ENVIRONMENT:
            continue
        try:
            operational_roots[name] = environment_path(name, environment)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
    sensitive_paths: dict[str, Path] = {
        "ELMOS_SPRING_BROKER_SECRET_ROOT": secret_root,
        "ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT": tls_root,
    }
    for name in SENSITIVE_PATH_ENVIRONMENTS:
        if name in sensitive_paths:
            continue
        try:
            sensitive_paths[name] = environment_path(name, environment)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
    validate_sensitive_path_isolation(errors, sensitive_paths, operational_roots)
    validate_operational_root_isolation(errors, operational_roots)

    secret_records: list[tuple[int, int, str | None]] = []
    for name in BROKER_SECRET_ENVIRONMENTS:
        try:
            path = environment_path(name, environment)
        except ValueError as error:
            errors.append(str(error))
            continue
        require(errors, path.parent == secret_root, f"{name} must be a direct child of ELMOS_SPRING_BROKER_SECRET_ROOT")
        inode = owner_only_file(
            errors,
            path,
            label=name,
            expected_uid=broker_uid,
            expected_gid=broker_gid,
            minimum_size=32,
            canonical_hmac_secret=True,
            expected_parent_uid=rootless_uid,
            expected_parent_gid=rootless_gid,
        )
        if inode:
            secret_records.append(inode)
    require(
        errors,
        len(secret_records) == 3
        and len({record[:2] for record in secret_records}) == 3,
        "broker HMAC copies must be three distinct files",
    )
    require(
        errors,
        len(secret_records) == 3
        and len({record[2] for record in secret_records}) == 3,
        "verifier, transformer, and runtime must use three distinct HMAC values",
    )

    try:
        tls_key = environment_path("ELMOS_SPRING_INGRESS_TLS_KEY_HOST_PATH", environment)
        require(errors, tls_key.parent == tls_root, "TLS key must be a direct child of ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT")
        owner_only_file(
            errors,
            tls_key,
            label="Spring ingress TLS key",
            expected_uid=ingress_uid,
            expected_gid=ingress_gid,
            minimum_size=32,
            maximum_size=65536,
            expected_parent_uid=rootless_uid,
            expected_parent_gid=rootless_gid,
        )
    except (TypeError, ValueError) as error:
        errors.append(str(error))

    try:
        certificate = environment_path("ELMOS_SPRING_INGRESS_TLS_CERT_HOST_PATH", environment)
        require(
            errors,
            certificate.parent == tls_root,
            "TLS certificate must be a direct child of ELMOS_SPRING_INGRESS_TLS_SECRET_ROOT",
        )
        trusted_regular_file(
            errors,
            certificate,
            label="Spring ingress TLS certificate",
            expected_uid=ingress_uid,
            expected_gid=ingress_gid,
            expected_parent_uid=rootless_uid,
            expected_parent_gid=rootless_gid,
            maximum_size=1024 * 1024,
        )
    except (TypeError, ValueError) as error:
        errors.append(str(error))

    try:
        installed_config = environment_path("ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH", environment)
        runner_env_file = environment_path("ELMOS_SPRING_RUNNER_ENV_FILE", environment)
        require(
            errors,
            installed_config.parent == runner_env_file.parent,
            "installed Spring ingress config and Runner environment must share one trusted parent",
        )
        trusted_regular_file(
            errors,
            installed_config,
            label="installed Spring ingress config",
            expected_uid=rootless_uid,
            expected_gid=rootless_gid,
            expected_parent_uid=rootless_uid,
            expected_parent_gid=rootless_gid,
            maximum_size=1024 * 1024,
            expected_sha256=EXPECTED_INGRESS_CONFIG_SHA256,
        )
    except (TypeError, ValueError) as error:
        errors.append(str(error))

    try:
        env_file = environment_path("ELMOS_SPRING_RUNNER_ENV_FILE", environment)
        owner_only_file(
            errors,
            env_file,
            label="Spring runner env file",
            expected_uid=rootless_uid,
            expected_gid=rootless_gid,
            maximum_size=65536,
            expected_parent_uid=rootless_uid,
            expected_parent_gid=rootless_gid,
        )
    except (TypeError, ValueError) as error:
        errors.append(str(error))

    for name in (
        "ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH",
        "ELMOS_COMMAND_ARTIFACT_HOST_PATH",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
        "ELMOS_VERIFIER_EVIDENCE_HOST_PATH",
    ):
        try:
            ordinary_directory(
                errors,
                environment_path(name, environment),
                label=name,
                allowed_uids={0, os.getuid(), rootless_uid, broker_uid},
                allowed_gids={0, os.getgid(), rootless_gid, broker_gid},
            )
        except ValueError as error:
            errors.append(str(error))

    trusted_unix_socket(
        errors,
        socket_path,
        expected_uid=rootless_uid,
        expected_gid=rootless_gid,
    )

    for name in IMAGE_ENVIRONMENTS:
        require(errors, bool(PINNED_IMAGE.fullmatch(environment.get(name, ""))), f"{name} must be name@sha256:<64 lowercase hex>")
    for name in CHILD_IMAGE_DIGEST_ENVIRONMENTS:
        require(errors, bool(SHA256_ID.fullmatch(environment.get(name, ""))), f"{name} must be sha256:<64 lowercase hex>")

    try:
        security_options = command_json(
            docker_command(socket_path, "info", "--format", "{{json .SecurityOptions}}")
        )
        require(
            errors,
            isinstance(security_options, list)
            and any(str(item).split(",", 1)[0] == "name=rootless" for item in security_options),
            "Docker daemon SecurityOptions must contain name=rootless",
        )
    except (RuntimeError, json.JSONDecodeError) as error:
        errors.append(str(error))

    for name in IMAGE_ENVIRONMENTS + CHILD_IMAGE_DIGEST_ENVIRONMENTS:
        reference = environment.get(name, "")
        if (name in IMAGE_ENVIRONMENTS and not PINNED_IMAGE.fullmatch(reference)) or (
            name in CHILD_IMAGE_DIGEST_ENVIRONMENTS and not SHA256_ID.fullmatch(reference)
        ):
            continue
        try:
            inspected = command_json(docker_command(socket_path, "image", "inspect", reference))
            require(
                errors,
                isinstance(inspected, list) and len(inspected) == 1,
                f"{name} must resolve to exactly one pre-pulled image",
            )
            if name in CHILD_IMAGE_DIGEST_ENVIRONMENTS and isinstance(inspected, list) and inspected:
                require(errors, inspected[0].get("Id") == reference, f"{name} local image ID mismatch")
            if name in IMAGE_ENVIRONMENTS and isinstance(inspected, list) and inspected:
                require(
                    errors,
                    reference in (inspected[0].get("RepoDigests") or []),
                    f"{name} RepoDigest mismatch",
                )
        except (RuntimeError, json.JSONDecodeError) as error:
            errors.append(str(error))

    control_network = environment.get("ELMOS_SPRING_RUNNER_CONTROL_NETWORK", "").strip()
    if not control_network:
        errors.append("ELMOS_SPRING_RUNNER_CONTROL_NETWORK is required")
    else:
        try:
            inspected = command_json(docker_command(socket_path, "network", "inspect", control_network))
            record = inspected[0] if isinstance(inspected, list) and inspected else {}
            labels = record.get("Labels") or {}
            require(errors, record.get("Internal") is True, "Spring control network must be internal")
            require(errors, labels.get("io.elmos.network.default-deny") == "true", "Spring control network must carry default-deny=true label")
            require(errors, labels.get("io.elmos.network.purpose") == "spring-runner-control", "Spring control network purpose label mismatch")
        except (RuntimeError, json.JSONDecodeError) as error:
            errors.append(str(error))

    return errors


def compose_value(value: Any, environment: Mapping[str, str]) -> str:
    """Resolve the small, full-value interpolation grammar used by Runner Compose."""

    text = str(value)
    match = COMPOSE_INTERPOLATION.fullmatch(text)
    if match is None:
        if "${" in text:
            raise ValueError("Runner Compose contains unsupported interpolation")
        return text
    name = match.group("name")
    configured = environment.get(name, "")
    operator = match.group("operator")
    if configured:
        return configured
    if operator == "-":
        return match.group("fallback")
    raise ValueError(f"Runner Compose requires {name}")


def environment_entries(
    errors: list[str], entries: Any, *, label: str
) -> dict[str, str] | None:
    if entries is None:
        return {}
    if not isinstance(entries, list):
        errors.append(f"{label} environment must be a list")
        return None
    values: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, str) or "=" not in entry:
            errors.append(f"{label} environment contains a malformed entry")
            return None
        name, value = entry.split("=", 1)
        if not name or name in values:
            errors.append(f"{label} environment contains a duplicate or empty name")
            return None
        values[name] = value
    return values


def expected_service_environment(
    service: Mapping[str, Any],
    image_record: Mapping[str, Any],
    environment: Mapping[str, str],
    errors: list[str],
    *,
    label: str,
) -> dict[str, str] | None:
    image_config = image_record.get("Config", {})
    if not isinstance(image_config, dict):
        errors.append(f"{label} image Config must be an object")
        return None
    result = environment_entries(
        errors, image_config.get("Env"), label=f"{label} image"
    )
    if result is None:
        return None
    declared = service.get("environment", {})
    if not isinstance(declared, dict):
        errors.append(f"{label} Compose environment must be an object")
        return None
    try:
        for name, value in declared.items():
            result[str(name)] = compose_value(value, environment)
    except ValueError as error:
        errors.append(str(error))
        return None
    return result


def compose_network_name(
    compose: Mapping[str, Any], logical_name: str, environment: Mapping[str, str]
) -> str:
    networks = compose.get("networks", {})
    if not isinstance(networks, dict):
        raise TypeError("Runner Compose networks must be an object")
    definition = networks.get(logical_name, {})
    if not isinstance(definition, dict):
        raise TypeError(f"Runner Compose network {logical_name} is invalid")
    configured = definition.get("name")
    if configured is None:
        return f"elmos-spring-runner_{logical_name}"
    return compose_value(configured, environment)


def expected_service_networks(
    compose: Mapping[str, Any],
    service: Mapping[str, Any],
    environment: Mapping[str, str],
) -> list[str]:
    declared = service.get("networks", [])
    if isinstance(declared, dict) or (
        isinstance(declared, list) and all(isinstance(item, str) for item in declared)
    ):
        logical_names = list(declared)
    else:
        raise ValueError("Runner service networks must be a string list or object")
    resolved = [compose_network_name(compose, name, environment) for name in logical_names]
    if len(set(resolved)) != len(resolved):
        raise ValueError(
            "Runner logical networks must resolve to distinct actual network names"
        )
    return resolved


def validate_resolved_network_isolation(
    errors: list[str],
    compose: Mapping[str, Any],
    environment: Mapping[str, str],
) -> None:
    """Prevent an external control network from collapsing into another trust zone."""

    networks = compose.get("networks", {})
    if not isinstance(networks, dict):
        errors.append("Runner Compose networks must be an object")
        return
    resolved: dict[str, str] = {}
    try:
        for logical_name in networks:
            resolved[str(logical_name)] = compose_network_name(
                compose, str(logical_name), environment
            )
    except (TypeError, ValueError) as error:
        errors.append(str(error))
        return
    duplicates = sorted(
        name for name, count in Counter(resolved.values()).items() if count > 1
    )
    require(
        errors,
        not duplicates,
        "Runner logical networks must resolve to distinct actual names: "
        + ", ".join(duplicates),
    )


def expected_service_mounts(
    service: Mapping[str, Any], environment: Mapping[str, str]
) -> dict[str, tuple[str, bool]]:
    result: dict[str, tuple[str, bool]] = {}
    for mount in service_volumes(service):
        target = mount.get("target")
        source = mount.get("source")
        if not isinstance(target, str) or not isinstance(source, str) or target in result:
            raise ValueError("Runner Compose mounts must have unique string source/target pairs")
        result[target] = (
            compose_value(source, environment),
            not bool(mount.get("read_only")),
        )
    return result


def container_port_key(value: Any, protocol: str = "tcp") -> str:
    text = str(value)
    if "/" in text:
        port, declared_protocol = text.rsplit("/", 1)
        text = port
        protocol = declared_protocol
    if not text.isdigit() or not 1 <= int(text) <= 65535 or protocol not in {"tcp", "udp"}:
        raise ValueError("Runner Compose contains an invalid exposed port")
    return f"{int(text)}/{protocol}"


def expected_exposed_ports(
    service: Mapping[str, Any], image_record: Mapping[str, Any]
) -> set[str]:
    image_config = image_record.get("Config", {})
    if not isinstance(image_config, dict):
        raise TypeError("Runner image Config must be an object")
    image_ports = image_config.get("ExposedPorts") or {}
    if not isinstance(image_ports, dict):
        raise TypeError("Runner image ExposedPorts must be an object")
    result = {container_port_key(item) for item in image_ports}
    exposed = service.get("expose", [])
    if not isinstance(exposed, list):
        raise TypeError("Runner Compose expose must be a list")
    result.update(container_port_key(item) for item in exposed)
    ports = service.get("ports", [])
    if not isinstance(ports, list):
        raise TypeError("Runner Compose ports must be a list")
    for port in ports:
        if not isinstance(port, dict):
            raise TypeError("Runner Compose long-form ports are required")
        result.add(container_port_key(port.get("target"), str(port.get("protocol", "tcp"))))
    return result


def duration_nanoseconds(value: Any) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)(ns|us|ms|s|m|h)", str(value))
    if match is None:
        raise ValueError("Runner Compose health duration is invalid")
    multipliers = {
        "ns": 1,
        "us": 1_000,
        "ms": 1_000_000,
        "s": 1_000_000_000,
        "m": 60 * 1_000_000_000,
        "h": 60 * 60 * 1_000_000_000,
    }
    return int(match.group(1)) * multipliers[match.group(2)]


def normalized_healthcheck(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("Runner healthcheck must be an object")
    allowed = {
        "Test",
        "Interval",
        "Timeout",
        "StartPeriod",
        "StartInterval",
        "Retries",
    }
    if set(value) - allowed:
        raise ValueError("Runner healthcheck contains undeclared fields")
    test = value.get("Test")
    if not isinstance(test, list) or not test or not all(
        isinstance(item, str) for item in test
    ):
        raise TypeError("Runner healthcheck Test must be a non-empty string array")
    result: dict[str, Any] = {"Test": list(test)}
    for name in ("Interval", "Timeout", "StartPeriod", "StartInterval", "Retries"):
        configured = value.get(name, 0)
        if (
            not isinstance(configured, int)
            or isinstance(configured, bool)
            or configured < 0
        ):
            raise TypeError(f"Runner healthcheck {name} must be a non-negative integer")
        result[name] = configured
    return result


def expected_runtime_healthcheck(
    service_name: str, image_record: Mapping[str, Any]
) -> dict[str, Any] | None:
    declared = RUNNER_SERVICE_HEALTHCHECK_CONTRACT[service_name]
    if declared is None:
        image_config = image_record.get("Config", {})
        if not isinstance(image_config, dict):
            raise TypeError("Runner image Config must be an object")
        return normalized_healthcheck(image_config.get("Healthcheck"))
    return normalized_healthcheck(
        {
            "Test": declared["test"],
            "Interval": duration_nanoseconds(declared["interval"]),
            "Timeout": duration_nanoseconds(declared["timeout"]),
            "StartPeriod": duration_nanoseconds(declared["start_period"]),
            "Retries": declared["retries"],
        }
    )


def published_port_bindings(
    errors: list[str], raw: Any, *, label: str
) -> list[tuple[str, str, str]] | None:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        errors.append(f"{label} port bindings must be an object")
        return None
    result: list[tuple[str, str, str]] = []
    for container_port, bindings in raw.items():
        if bindings is None or bindings == []:
            continue
        if not isinstance(bindings, list):
            errors.append(f"{label} port bindings contain a malformed list")
            return None
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append(f"{label} port bindings contain a malformed record")
                return None
            host_ip = binding.get("HostIp")
            host_port = binding.get("HostPort")
            if not isinstance(host_ip, str) or not isinstance(host_port, str):
                errors.append(f"{label} port binding lacks an exact host IP or port")
                return None
            result.append((str(container_port), host_ip, host_port))
    return sorted(result)


def validate_runtime_mounts(
    errors: list[str],
    *,
    service_name: str,
    actual: Any,
    expected: Mapping[str, tuple[str, bool]],
) -> None:
    if not isinstance(actual, list):
        errors.append(f"{service_name} runtime mounts must be a list")
        return
    by_target: dict[str, Mapping[str, Any]] = {}
    for mount in actual:
        if not isinstance(mount, dict) or not isinstance(mount.get("Destination"), str):
            errors.append(f"{service_name} runtime mounts contain a malformed record")
            return
        target = mount["Destination"]
        if target in by_target:
            errors.append(f"{service_name} runtime mounts contain a duplicate destination")
            return
        by_target[target] = mount
    require(
        errors,
        set(by_target) == set(expected),
        f"{service_name} runtime mount inventory drift",
    )
    for target, (source, read_write) in expected.items():
        mount = by_target.get(target)
        if mount is None:
            continue
        require(errors, mount.get("Type") == "bind", f"{service_name} mount {target} must remain a bind mount")
        require(errors, mount.get("Source") == source, f"{service_name} mount {target} source drift")
        require(errors, mount.get("RW") is read_write, f"{service_name} mount {target} access mode drift")
        require(
            errors,
            mount.get("Mode") == ("rw" if read_write else "ro"),
            f"{service_name} mount {target} mode drift",
        )
        require(
            errors,
            mount.get("Propagation") == "rprivate",
            f"{service_name} mount {target} propagation drift",
        )


MountObjectIdentity = tuple[int, int, int, int, int, int]
ProcessIdentity = tuple[int, int, int, str, int, int]
LiveMountObservation = tuple[
    MountObjectIdentity,
    MountObjectIdentity,
    ProcessIdentity,
    ProcessIdentity,
]
LiveMountObserver = Callable[[str, int, str, str], LiveMountObservation]
LiveProcessObserver = Callable[[int, str], ProcessIdentity]


def mount_object_identity(details: os.stat_result) -> MountObjectIdentity:
    """Stable bind-object identity that ignores active-directory timestamps."""

    return (
        details.st_dev,
        details.st_ino,
        stat.S_IFMT(details.st_mode),
        stat.S_IMODE(details.st_mode),
        details.st_uid,
        details.st_gid,
    )


def read_proc_stat_start_time(process_descriptor: int, *, label: str) -> str:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open("stat", flags, dir_fd=process_descriptor)
        chunks: list[bytes] = []
        total = 0
        while total <= 16 * 1024:
            chunk = os.read(descriptor, min(4096, 16 * 1024 + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > 16 * 1024:
            raise RuntimeError(f"{label} process stat exceeds the byte budget")
        rendered = b"".join(chunks).decode("ascii", errors="strict").strip()
    except (OSError, UnicodeError) as error:
        raise RuntimeError(f"{label} process stat could not be read safely") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    close_parenthesis = rendered.rfind(")")
    fields = rendered[close_parenthesis + 1 :].strip().split()
    if close_parenthesis < 2 or len(fields) < 20 or not fields[19].isdigit():
        raise RuntimeError(f"{label} process stat identity is invalid")
    return fields[19]


def live_process_identity(
    process_descriptor: int, process_id: int, *, label: str
) -> ProcessIdentity:
    try:
        process_details = os.fstat(process_descriptor)
        namespace_details = os.stat(
            "ns/mnt", dir_fd=process_descriptor, follow_symlinks=True
        )
    except OSError as error:
        raise RuntimeError(f"{label} mount namespace identity could not be read") from error
    return (
        process_id,
        process_details.st_dev,
        process_details.st_ino,
        read_proc_stat_start_time(process_descriptor, label=label),
        namespace_details.st_dev,
        namespace_details.st_ino,
    )


def observe_live_process_identity(process_id: int, label: str) -> ProcessIdentity:
    """Capture one Linux process generation and mount-namespace identity."""

    if sys.platform != "linux" or not hasattr(os, "O_PATH"):
        raise RuntimeError("live Runner process identity validation requires Linux O_PATH and /proc")
    if type(process_id) is not int or process_id <= 1:
        raise RuntimeError(f"{label} process ID is invalid")
    directory_flags = (
        os.O_PATH
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    proc_descriptor = -1
    process_descriptor = -1
    try:
        proc_descriptor = os.open("/proc", directory_flags)
        process_descriptor = os.open(
            str(process_id), directory_flags, dir_fd=proc_descriptor
        )
        return live_process_identity(process_descriptor, process_id, label=label)
    except OSError as error:
        raise RuntimeError(f"{label} process identity could not be captured safely") from error
    finally:
        if process_descriptor >= 0:
            os.close(process_descriptor)
        if proc_descriptor >= 0:
            os.close(proc_descriptor)


def observe_live_bind_mount(
    source: str,
    process_id: int,
    destination: str,
    label: str,
) -> LiveMountObservation:
    """Bind the current host object to the object visible in a live container."""

    if sys.platform != "linux" or not hasattr(os, "O_PATH"):
        raise RuntimeError("live Runner mount identity validation requires Linux O_PATH and /proc")
    if type(process_id) is not int or process_id <= 1:
        raise RuntimeError(f"{label} process ID is invalid")
    if (
        not isinstance(source, str)
        or not source
        or source != source.strip()
    ):
        raise RuntimeError(f"{label} host source is not a normalized absolute non-root path")
    if (
        not isinstance(destination, str)
        or not destination
        or destination != destination.strip()
    ):
        raise RuntimeError(f"{label} container destination is invalid")
    source_path = Path(source)
    destination_path = Path(destination)
    if (
        not source_path.is_absolute()
        or source_path == Path("/")
        or source_path != Path(os.path.normpath(source_path))
    ):
        raise RuntimeError(f"{label} host source is not a normalized absolute non-root path")
    if (
        not destination_path.is_absolute()
        or destination_path == Path("/")
        or destination_path != Path(os.path.normpath(destination_path))
    ):
        raise RuntimeError(f"{label} container destination is invalid")

    directory_flags = (
        os.O_PATH
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_DIRECTORY", 0)
    )
    object_flags = os.O_PATH | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_magic_flags = os.O_PATH | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    source_ancestors: list[int] = []
    target_ancestors: list[int] = []
    source_descriptor = -1
    proc_descriptor = -1
    process_descriptor = -1
    target_descriptor = -1
    try:
        current = os.open(source_path.anchor, directory_flags)
        source_ancestors.append(current)
        for part in source_path.parts[1:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            source_ancestors.append(current)
        source_descriptor = os.open(
            source_path.parts[-1], object_flags, dir_fd=source_ancestors[-1]
        )
        source_before = os.fstat(source_descriptor)
        if not (
            stat.S_ISREG(source_before.st_mode)
            or stat.S_ISDIR(source_before.st_mode)
            or stat.S_ISSOCK(source_before.st_mode)
        ):
            raise RuntimeError(f"{label} host source has an unsupported object type")
        source_ancestor_before = [
            stable_directory_identity(os.fstat(descriptor))
            for descriptor in source_ancestors
        ]

        proc_descriptor = os.open("/proc", directory_flags)
        process_descriptor = os.open(
            str(process_id), directory_flags, dir_fd=proc_descriptor
        )
        process_before = live_process_identity(
            process_descriptor, process_id, label=label
        )
        # /proc/<pid>/root is an intentional kernel magic link into the already
        # authenticated process mount namespace. Components below it remain
        # no-follow O_PATH descriptors.
        current = os.open("root", root_magic_flags, dir_fd=process_descriptor)
        target_ancestors.append(current)
        for part in destination_path.parts[1:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            target_ancestors.append(current)
        target_descriptor = os.open(
            destination_path.parts[-1], object_flags, dir_fd=target_ancestors[-1]
        )
        target_before = os.fstat(target_descriptor)
        target_ancestor_before = [
            stable_directory_identity(os.fstat(descriptor))
            for descriptor in target_ancestors
        ]
        if not (
            stat.S_ISREG(target_before.st_mode)
            or stat.S_ISDIR(target_before.st_mode)
            or stat.S_ISSOCK(target_before.st_mode)
        ):
            raise RuntimeError(f"{label} container target has an unsupported object type")

        source_path_after = os.stat(
            source_path.parts[-1],
            dir_fd=source_ancestors[-1],
            follow_symlinks=False,
        )
        source_ancestor_after = [
            stable_directory_identity(os.fstat(descriptor))
            for descriptor in source_ancestors
        ]
        source_ancestor_paths_after = [
            stable_directory_identity(os.stat(source_path.anchor, follow_symlinks=False))
        ]
        for index, part in enumerate(source_path.parts[1:-1]):
            source_ancestor_paths_after.append(
                stable_directory_identity(
                    os.stat(
                        part,
                        dir_fd=source_ancestors[index],
                        follow_symlinks=False,
                    )
                )
            )
        source_after = os.fstat(source_descriptor)
        target_after = os.fstat(target_descriptor)
        target_ancestor_after = [
            stable_directory_identity(os.fstat(descriptor))
            for descriptor in target_ancestors
        ]
        target_ancestor_paths_after = [
            stable_directory_identity(os.fstat(target_ancestors[0]))
        ]
        for index, part in enumerate(destination_path.parts[1:-1]):
            target_ancestor_paths_after.append(
                stable_directory_identity(
                    os.stat(
                        part,
                        dir_fd=target_ancestors[index],
                        follow_symlinks=False,
                    )
                )
            )
        target_path_after = os.stat(
            destination_path.parts[-1],
            dir_fd=target_ancestors[-1],
            follow_symlinks=False,
        )
        process_after = live_process_identity(
            process_descriptor, process_id, label=label
        )
        host_identity = mount_object_identity(source_before)
        target_identity = mount_object_identity(target_before)
        if (
            host_identity != mount_object_identity(source_after)
            or host_identity != mount_object_identity(source_path_after)
            or source_ancestor_before != source_ancestor_after
            or source_ancestor_before != source_ancestor_paths_after
        ):
            raise RuntimeError(f"{label} host source or ancestry changed during validation")
        if (
            target_identity != mount_object_identity(target_after)
            or target_identity != mount_object_identity(target_path_after)
            or target_ancestor_before != target_ancestor_after
            or target_ancestor_before != target_ancestor_paths_after
        ):
            raise RuntimeError(f"{label} container target or ancestry changed during validation")
        return host_identity, target_identity, process_before, process_after
    except OSError as error:
        raise RuntimeError(f"{label} live mount identity could not be captured safely") from error
    finally:
        for descriptor in (target_descriptor, process_descriptor, proc_descriptor, source_descriptor):
            if descriptor >= 0:
                os.close(descriptor)
        for descriptor in reversed(target_ancestors):
            os.close(descriptor)
        for descriptor in reversed(source_ancestors):
            os.close(descriptor)


def validate_live_mount_identities(
    errors: list[str],
    *,
    records: Mapping[str, Mapping[str, Any]],
    compose: Mapping[str, Any],
    environment: Mapping[str, str],
    observer: LiveMountObserver,
    process_observer: LiveProcessObserver,
) -> dict[str, ProcessIdentity]:
    """Validate every exact bind mount and return one stable process token/service."""

    services = compose.get("services", {})
    if not isinstance(services, dict):
        errors.append("runner Compose services must be an object")
        return {}
    identities: dict[str, ProcessIdentity] = {}
    for service_name in sorted(EXPECTED_RUNNER_SERVICES):
        service = services.get(service_name)
        record = records.get(service_name)
        if not isinstance(service, dict) or not isinstance(record, Mapping):
            errors.append(f"{service_name} live mount inputs are incomplete")
            continue
        state = record.get("State")
        process_id = state.get("Pid") if isinstance(state, dict) else None
        if type(process_id) is not int or process_id <= 1:
            errors.append(f"{service_name} runtime process ID must be a positive host PID")
            continue
        try:
            service_identity = process_observer(
                process_id, f"{service_name} live process"
            )
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            errors.append(f"{service_name} live process identity failed: {error}")
            continue
        try:
            mounts = expected_service_mounts(service, environment)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
            continue
        for destination, (source, _read_write) in sorted(mounts.items()):
            label = f"{service_name} mount {destination}"
            try:
                observation = observer(source, process_id, destination, label)
                if not isinstance(observation, tuple) or len(observation) != 4:
                    raise TypeError("observer returned an invalid record")
                host_identity, target_identity, process_before, process_after = observation
                if host_identity != target_identity:
                    raise RuntimeError(
                        "container target does not expose the current host source object"
                    )
                if process_before != process_after:
                    raise RuntimeError("container process or mount namespace changed")
                if service_identity != process_before:
                    raise RuntimeError(
                        "container process or mount namespace changed between mounts"
                    )
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                errors.append(f"{label} live identity failed: {error}")
        try:
            completed_identity = process_observer(
                process_id, f"{service_name} completed live process"
            )
            if completed_identity != service_identity:
                raise RuntimeError(
                    "container process or mount namespace changed during live mount validation"
                )
            identities[service_name] = service_identity
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            errors.append(f"{service_name} final live process identity failed: {error}")
    return identities


def runtime_generation(record: Mapping[str, Any], *, label: str) -> tuple[Any, ...]:
    """Stable projection used to reject restarts or mount drift during inspection."""

    state = record.get("State")
    host = record.get("HostConfig")
    mounts = record.get("Mounts")
    if not isinstance(state, dict) or not isinstance(host, dict) or not isinstance(mounts, list):
        raise TypeError(f"{label} runtime generation fields are malformed")
    process_id = state.get("Pid")
    started_at = state.get("StartedAt")
    restart_count = record.get("RestartCount")
    if type(process_id) is not int or process_id <= 1:
        raise ValueError(f"{label} State.Pid must be a positive host PID")
    if not isinstance(started_at, str) or not started_at:
        raise ValueError(f"{label} State.StartedAt is required")
    if type(restart_count) is not int or restart_count < 0:
        raise ValueError(f"{label} RestartCount must be a non-negative integer")
    mount_projection: list[tuple[Any, ...]] = []
    for mount in mounts:
        if not isinstance(mount, dict):
            raise TypeError(f"{label} mount generation record is malformed")
        mount_projection.append(
            tuple(
                mount.get(name)
                for name in ("Type", "Source", "Destination", "RW", "Mode", "Propagation")
            )
        )
    binds = host.get("Binds")
    if not isinstance(binds, list) or not all(isinstance(item, str) for item in binds):
        raise TypeError(f"{label} HostConfig.Binds generation is malformed")
    return (
        record.get("Id"),
        record.get("Image"),
        process_id,
        started_at,
        restart_count,
        tuple(sorted(mount_projection, key=repr)),
        tuple(sorted(binds)),
    )


def validate_runtime_service(
    errors: list[str],
    *,
    service_name: str,
    service: Mapping[str, Any],
    compose: Mapping[str, Any],
    record: Mapping[str, Any],
    image_record: Mapping[str, Any],
    environment: Mapping[str, str],
    bind_address: str,
    bind_port: int,
) -> None:
    config = record.get("Config", {})
    host = record.get("HostConfig", {})
    network_settings = record.get("NetworkSettings", {})
    state = record.get("State", {})
    if not all(isinstance(item, dict) for item in (config, host, network_settings, state)):
        errors.append(f"{service_name} inspect record is incomplete")
        return

    image_environment = SERVICE_IMAGE_ENVIRONMENTS[service_name]
    expected_image = environment.get(image_environment, "")
    require(errors, config.get("Image") == expected_image, f"{service_name} runtime image reference drift")
    require(errors, image_record.get("Id") == record.get("Image"), f"{service_name} runtime image ID drift")
    require(
        errors,
        expected_image in (image_record.get("RepoDigests") or []),
        f"{service_name} runtime image RepoDigest drift",
    )
    require(errors, config.get("User") == SERVICE_USERS[service_name], f"{service_name} runtime user drift")

    image_config = image_record.get("Config", {})
    if not isinstance(image_config, dict):
        errors.append(f"{service_name} image Config must be an object")
    else:
        expected_entrypoint = service.get("entrypoint", image_config.get("Entrypoint"))
        expected_command = service.get("command", image_config.get("Cmd"))
        require(errors, config.get("Entrypoint") == expected_entrypoint, f"{service_name} runtime Entrypoint drift")
        require(errors, config.get("Cmd") == expected_command, f"{service_name} runtime Cmd drift")
        expected_working_directory = service.get(
            "working_dir", image_config.get("WorkingDir", "")
        )
        require(
            errors,
            config.get("WorkingDir", "") == expected_working_directory,
            f"{service_name} runtime working directory drift",
        )
        process_parts: list[str] = []
        for value in (expected_entrypoint, expected_command):
            if value is None:
                continue
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                errors.append(
                    f"{service_name} controlled image process must use exec-form arrays"
                )
                process_parts = []
                break
            process_parts.extend(value)
        if process_parts:
            require(errors, record.get("Path") == process_parts[0], f"{service_name} runtime process path drift")
            require(errors, record.get("Args") == process_parts[1:], f"{service_name} runtime process arguments drift")
        try:
            exposed_ports = expected_exposed_ports(service, image_record)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
            exposed_ports = set()
        actual_exposed_ports = config.get("ExposedPorts") or {}
        require(
            errors,
            isinstance(actual_exposed_ports, dict)
            and set(actual_exposed_ports) == exposed_ports,
            f"{service_name} runtime exposed port inventory drift",
        )

    expected_environment = expected_service_environment(
        service,
        image_record,
        environment,
        errors,
        label=service_name,
    )
    actual_environment = environment_entries(
        errors, config.get("Env"), label=f"{service_name} runtime"
    )
    if expected_environment is not None and actual_environment is not None:
        require(
            errors,
            actual_environment == expected_environment,
            f"{service_name} runtime environment drift",
        )
    try:
        expected_healthcheck = expected_runtime_healthcheck(
            service_name, image_record
        )
        actual_healthcheck = normalized_healthcheck(config.get("Healthcheck"))
        require(
            errors,
            actual_healthcheck == expected_healthcheck,
            f"{service_name} runtime healthcheck configuration drift",
        )
    except (TypeError, ValueError) as error:
        errors.append(str(error))
        expected_healthcheck = None

    require(errors, host.get("Privileged") is False, f"{service_name} must not be privileged")
    require(errors, host.get("ReadonlyRootfs") is True, f"{service_name} runtime root filesystem must be read-only")
    require(errors, host.get("AutoRemove") is False, f"{service_name} runtime AutoRemove drift")
    require(errors, host.get("Init") is True, f"{service_name} runtime init contract drift")
    require(
        errors,
        host.get("PidsLimit") == service.get("pids_limit"),
        f"{service_name} runtime PID limit drift",
    )
    for field, expected in RUNNER_SERVICE_RUNTIME_RESOURCE_CONTRACT[service_name].items():
        require(
            errors,
            type(host.get(field)) is int and host.get(field) == expected,
            f"{service_name} runtime {field} resource limit drift",
        )
    require(
        errors,
        host.get("LogConfig")
        == {
            "Type": RUNNER_LOGGING_CONTRACT["driver"],
            "Config": RUNNER_LOGGING_CONTRACT["options"],
        },
        f"{service_name} runtime logging contract drift",
    )
    require(errors, host.get("CapAdd") in (None, []), f"{service_name} runtime must not add capabilities")
    require(errors, host.get("CapDrop") == ["ALL"], f"{service_name} runtime must drop exactly all capabilities")
    require(
        errors,
        host.get("SecurityOpt") == ["no-new-privileges:true"],
        f"{service_name} runtime security options drift",
    )
    require(errors, host.get("PublishAllPorts") is False, f"{service_name} must not publish undeclared ports")
    expected_groups = ["0"] if service_name == "spring-runner-broker" else []
    require(
        errors,
        (host.get("GroupAdd") or []) == expected_groups,
        f"{service_name} supplementary groups drift",
    )
    exact_namespaces = {
        "PidMode": "",
        "IpcMode": "private",
        "UTSMode": "",
        "UsernsMode": "",
        "CgroupnsMode": "private",
    }
    for field, expected in exact_namespaces.items():
        require(
            errors,
            host.get(field) == expected,
            f"{service_name} {field} runtime namespace drift",
        )
    for field in (
        "Devices",
        "DeviceRequests",
        "VolumesFrom",
        "Links",
        "ExtraHosts",
        "Dns",
        "DnsOptions",
        "DnsSearch",
    ):
        require(
            errors,
            host.get(field) in (None, []),
            f"{service_name} runtime {field} must be empty",
        )
    require(
        errors,
        host.get("Sysctls") in (None, {}),
        f"{service_name} runtime Sysctls must be empty",
    )
    restart_policy = host.get("RestartPolicy") or {}
    require(
        errors,
        isinstance(restart_policy, dict)
        and restart_policy.get("Name") == "unless-stopped"
        and restart_policy.get("MaximumRetryCount", 0) == 0,
        f"{service_name} runtime restart policy drift",
    )

    try:
        expected_networks = expected_service_networks(compose, service, environment)
    except (TypeError, ValueError) as error:
        errors.append(str(error))
        expected_networks = []
    if expected_networks:
        require(
            errors,
            host.get("NetworkMode") in expected_networks,
            f"{service_name} runtime primary network must select a controlled network",
        )
        actual_networks = network_settings.get("Networks", {})
        require(
            errors,
            isinstance(actual_networks, dict)
            and set(actual_networks) == set(expected_networks),
            f"{service_name} runtime network membership drift",
        )

    expected_bindings = (
        [("8443/tcp", bind_address, str(bind_port))]
        if service_name == "spring-runner-ingress"
        else []
    )
    expected_binding_object = (
        {"8443/tcp": [{"HostIp": bind_address, "HostPort": str(bind_port)}]}
        if service_name == "spring-runner-ingress"
        else {}
    )
    host_bindings = published_port_bindings(
        errors, host.get("PortBindings"), label=f"{service_name} HostConfig"
    )
    runtime_bindings = published_port_bindings(
        errors, network_settings.get("Ports"), label=f"{service_name} NetworkSettings"
    )
    if host_bindings is not None:
        require(errors, host_bindings == expected_bindings, f"{service_name} HostConfig port bindings drift")
        require(
            errors,
            (host.get("PortBindings") or {}) == expected_binding_object,
            f"{service_name} HostConfig port binding shape drift",
        )
    if runtime_bindings is not None:
        require(errors, runtime_bindings == expected_bindings, f"{service_name} runtime published ports drift")
        try:
            all_exposed_ports = expected_exposed_ports(service, image_record)
        except (TypeError, ValueError):
            all_exposed_ports = set()
        expected_runtime_ports: dict[str, Any] = {
            name: None for name in all_exposed_ports
        }
        expected_runtime_ports.update(expected_binding_object)
        require(
            errors,
            (network_settings.get("Ports") or {}) == expected_runtime_ports,
            f"{service_name} runtime port inventory drift",
        )

    try:
        expected_mounts = expected_service_mounts(service, environment)
    except ValueError as error:
        errors.append(str(error))
        expected_mounts = {}
    validate_runtime_mounts(
        errors,
        service_name=service_name,
        actual=record.get("Mounts"),
        expected=expected_mounts,
    )
    expected_binds = sorted(
        f"{source}:{target}:{'rw' if read_write else 'ro'}"
        for target, (source, read_write) in expected_mounts.items()
    )
    actual_binds = host.get("Binds")
    require(
        errors,
        isinstance(actual_binds, list)
        and sorted(actual_binds) == expected_binds
        and len(actual_binds) == len(expected_binds),
        f"{service_name} runtime bind inventory drift",
    )
    expected_tmpfs = {
        str(item).split(":", 1)[0]
        for item in service.get("tmpfs", [])
        if isinstance(item, str)
    }
    actual_tmpfs = host.get("Tmpfs") or {}
    require(
        errors,
        isinstance(actual_tmpfs, dict) and set(actual_tmpfs) == expected_tmpfs,
        f"{service_name} runtime tmpfs inventory drift",
    )
    if isinstance(actual_tmpfs, dict):
        for target, options in actual_tmpfs.items():
            rendered_options = str(options).split(",")
            size_options = [
                item for item in rendered_options if item.startswith("size=")
            ]
            non_size_options = [
                item for item in rendered_options if not item.startswith("size=")
            ]
            require(
                errors,
                len(non_size_options) == 3
                and set(non_size_options) == {"rw", "noexec", "nosuid"}
                and len(size_options) == 1
                and size_options[0].removeprefix("size=")
                in RUNNER_SERVICE_TMPFS_SIZE_CONTRACT[service_name],
                f"{service_name} tmpfs {target} hardening drift",
            )

    labels = config.get("Labels") or {}
    require(
        errors,
        isinstance(labels, dict)
        and labels.get("com.docker.compose.project") == "elmos-spring-runner"
        and labels.get("com.docker.compose.service") == service_name,
        f"{service_name} Compose identity labels drift",
    )
    require(
        errors,
        state.get("Running") is True
        and state.get("Restarting") is False
        and state.get("Paused") is False
        and state.get("Dead") is False
        and state.get("OOMKilled") is False,
        f"{service_name} must be stably running",
    )
    health = state.get("Health")
    require(
        errors,
        (
            health is None
            if expected_healthcheck is None
            else isinstance(health, dict) and health.get("Status") == "healthy"
        ),
        f"{service_name} healthcheck is not healthy",
    )


def compose_container_ids(
    socket_path: Path,
    environment: Mapping[str, str],
    paths: ContractPaths | None = None,
) -> dict[str, str]:
    paths = paths or ContractPaths()
    env_file = environment_path("ELMOS_SPRING_RUNNER_ENV_FILE", environment)
    command = docker_command(
        socket_path,
        "compose",
        "--project-name",
        "elmos-spring-runner",
        "--env-file",
        str(env_file),
        "-f",
        str(paths.runner_compose),
        "ps",
        "--all",
        "--no-trunc",
        "--format",
        "json",
    )
    rows = command_json(command)
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise TypeError("docker compose ps did not return a JSON list")
    if len(rows) != 3 or not all(isinstance(row, dict) for row in rows):
        raise ValueError("docker compose ps must return exactly three container records")
    services = [str(row.get("Service", "")) for row in rows]
    identifiers = [str(row.get("ID", "")) for row in rows]
    counts = Counter(services)
    if counts != Counter({name: 1 for name in EXPECTED_RUNNER_SERVICES}):
        raise ValueError("docker compose ps must return exactly one container for each Runner service")
    if (
        any(re.fullmatch(r"[0-9a-f]{64}", identifier) is None for identifier in identifiers)
        or len(set(identifiers)) != 3
    ):
        raise ValueError("docker compose ps must return three distinct full container IDs")
    return dict(zip(services, identifiers, strict=True))


def validate_running(
    paths: ContractPaths | None = None,
    environment: Mapping[str, str] | None = None,
    *,
    _live_mount_observer: LiveMountObserver = observe_live_bind_mount,
    _live_process_observer: LiveProcessObserver = observe_live_process_identity,
) -> list[str]:
    paths = paths or ContractPaths()
    environment = environment if environment is not None else os.environ
    errors = validate_host(paths, environment)
    if errors:
        return errors
    try:
        socket_path = environment_path("ELMOS_ROOTLESS_DOCKER_SOCKET", environment)
        bind_address, bind_port = private_https_endpoint(environment)
        identifiers = compose_container_ids(socket_path, environment, paths)
    except (TypeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        errors.append(str(error))
        return errors
    records: dict[str, dict[str, Any]] = {}
    image_records: dict[str, dict[str, Any]] = {}
    for service, identifier in identifiers.items():
        try:
            inspected = command_json(docker_command(socket_path, "inspect", identifier))
            if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
                raise TypeError("docker inspect must return exactly one object")
            if inspected[0].get("Id") != identifier:
                raise TypeError("docker inspect container identity does not match Compose ps")
            records[service] = inspected[0]
            image_reference = environment[SERVICE_IMAGE_ENVIRONMENTS[service]]
            inspected_image = command_json(
                docker_command(socket_path, "image", "inspect", image_reference)
            )
            if (
                not isinstance(inspected_image, list)
                or len(inspected_image) != 1
                or not isinstance(inspected_image[0], dict)
            ):
                raise TypeError("docker image inspect must return exactly one object")
            image_records[service] = inspected_image[0]
        except (RuntimeError, json.JSONDecodeError, IndexError, TypeError) as error:
            errors.append(f"{service} inspection failed: {error}")
    if set(records) != EXPECTED_RUNNER_SERVICES or set(image_records) != EXPECTED_RUNNER_SERVICES:
        return errors

    compose = read_yaml(paths.runner_compose)
    services = compose.get("services", {})
    if not isinstance(services, dict):
        return errors + ["runner Compose services must be an object"]
    for service in sorted(EXPECTED_RUNNER_SERVICES):
        service_config = services.get(service)
        if not isinstance(service_config, dict):
            errors.append(f"runner service {service} is missing")
            continue
        validate_runtime_service(
            errors,
            service_name=service,
            service=service_config,
            compose=compose,
            record=records[service],
            image_record=image_records[service],
            environment=environment,
            bind_address=bind_address,
            bind_port=bind_port,
        )

    if errors:
        return errors
    initial_generations: dict[str, tuple[Any, ...]] = {}
    try:
        initial_generations = {
            service: runtime_generation(records[service], label=service)
            for service in sorted(EXPECTED_RUNNER_SERVICES)
        }
    except (TypeError, ValueError) as error:
        errors.append(str(error))
        return errors
    initial_process_identities = validate_live_mount_identities(
        errors,
        records=records,
        compose=compose,
        environment=environment,
        observer=_live_mount_observer,
        process_observer=_live_process_observer,
    )
    if errors or set(initial_process_identities) != EXPECTED_RUNNER_SERVICES:
        if not errors:
            errors.append("Runner live mount process identities are incomplete")
        return errors

    for network_name in ("elmos-spring-runner-edge", "elmos-spring-runner-broker"):
        try:
            inspected = command_json(
                docker_command(socket_path, "network", "inspect", network_name)
            )
            record = (
                inspected[0]
                if isinstance(inspected, list)
                and len(inspected) == 1
                and isinstance(inspected[0], dict)
                else {}
            )
            require(
                errors,
                bool(record),
                f"running network {network_name} must resolve to exactly one object",
            )
            require(
                errors,
                record.get("Internal") is True,
                f"running network {network_name} must remain internal/default-deny",
            )
        except (RuntimeError, json.JSONDecodeError) as error:
            errors.append(str(error))

    if errors:
        return errors

    try:
        final_identifiers = compose_container_ids(socket_path, environment, paths)
        if final_identifiers != identifiers:
            errors.append("Runner Compose container identities changed during live validation")
            return errors
        final_records: dict[str, dict[str, Any]] = {}
        for service, identifier in sorted(final_identifiers.items()):
            inspected = command_json(docker_command(socket_path, "inspect", identifier))
            if (
                not isinstance(inspected, list)
                or len(inspected) != 1
                or not isinstance(inspected[0], dict)
                or inspected[0].get("Id") != identifier
            ):
                raise TypeError(
                    f"{service} stable Docker reinspection must return its exact container"
                )
            final_records[service] = inspected[0]
            service_config = services.get(service)
            if not isinstance(service_config, dict):
                raise TypeError(f"runner service {service} is missing during reinspection")
            validate_runtime_service(
                errors,
                service_name=service,
                service=service_config,
                compose=compose,
                record=final_records[service],
                image_record=image_records[service],
                environment=environment,
                bind_address=bind_address,
                bind_port=bind_port,
            )
            final_generation = runtime_generation(
                final_records[service], label=f"{service} stable reinspection"
            )
            require(
                errors,
                final_generation == initial_generations[service],
                f"{service} container generation changed during live validation",
            )
        if errors:
            return errors
        final_process_identities = validate_live_mount_identities(
            errors,
            records=final_records,
            compose=compose,
            environment=environment,
            observer=_live_mount_observer,
            process_observer=_live_process_observer,
        )
        require(
            errors,
            final_process_identities == initial_process_identities,
            "Runner process or mount namespace identities changed during live validation",
        )
    except (RuntimeError, json.JSONDecodeError, IndexError, KeyError, TypeError, ValueError) as error:
        errors.append(f"Runner stable reinspection failed: {error}")
    return errors


def emit(errors: Sequence[str], *, mode: str, as_json: bool) -> int:
    payload = {
        "status": "BLOCKED" if errors else "READY_FOR_EXTERNAL_GATE",
        "mode": mode,
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "errors": list(errors),
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print("SPRING_RUNNER_TOPOLOGY=READY_FOR_EXTERNAL_GATE")
        print(f"VALIDATION_MODE={mode}")
        print("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN")
        print("CERTIFICATION=NOT_CERTIFIED")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-host", action="store_true", help="inspect prepared rootless host without mutation")
    mode.add_argument("--check-running", action="store_true", help="inspect an already-running Runner deployment")
    parser.add_argument(
        "--environment-file",
        type=Path,
        help="parse an owner-only Runner environment file as inert allowlisted data",
    )
    parser.add_argument(
        "--rootless-owner-uid",
        type=int,
        help="independently supplied non-root UID that owns the rootless daemon and Runner env",
    )
    parser.add_argument(
        "--rootless-owner-gid",
        type=int,
        help="independently supplied non-root GID that owns the rootless daemon and Runner env",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if (args.check_host or args.check_running) and not args.environment_file:
        return emit(
            ["--check-host and --check-running require --environment-file; shell sourcing is forbidden"],
            mode="ENVIRONMENT_FILE_REQUIRED",
            as_json=args.json,
        )
    if args.check_host or args.check_running:
        if (
            type(args.rootless_owner_uid) is not int
            or args.rootless_owner_uid <= 0
            or type(args.rootless_owner_gid) is not int
            or args.rootless_owner_gid <= 0
        ):
            return emit(
                [
                    "--check-host and --check-running require positive --rootless-owner-uid and --rootless-owner-gid bindings"
                ],
                mode="ROOTLESS_OWNER_BINDING_REQUIRED",
                as_json=args.json,
            )
        if os.geteuid() != 0:
            return emit(
                [
                    "--check-host and --check-running require a controlled read-only root observer; the Docker daemon itself must remain rootless"
                ],
                mode="PRIVILEGED_OBSERVER_REQUIRED",
                as_json=args.json,
            )
    environment: Mapping[str, str] = os.environ
    environment_errors: list[str] = []
    if args.environment_file:
        environment, environment_errors = load_environment_file(
            args.environment_file,
            expected_owner_uid=(
                args.rootless_owner_uid
                if args.check_host or args.check_running
                else None
            ),
            expected_owner_gid=(
                args.rootless_owner_gid
                if args.check_host or args.check_running
                else None
            ),
        )
    if environment_errors:
        return emit(environment_errors, mode="ENVIRONMENT_FILE_REJECTED", as_json=args.json)
    if args.check_running:
        return emit(validate_running(environment=environment), mode="RUNNING_HOST_READ_ONLY", as_json=args.json)
    if args.check_host:
        return emit(validate_host(environment=environment), mode="PREPARED_HOST_READ_ONLY", as_json=args.json)
    return emit(validate_static(), mode="STATIC_CONTRACT_ONLY", as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
