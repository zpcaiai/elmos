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
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
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
EXPECTED_RUNNER_SERVICES = {
    "spring-runner-ingress",
    "spring-runner-broker",
    "spring-runner-egress-proxy",
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
    require(errors, service.get("read_only") is True, f"{name} root filesystem must be read-only")
    require(errors, service.get("cap_drop") == ["ALL"], f"{name} must drop all capabilities")
    require(
        errors,
        "no-new-privileges:true" in service.get("security_opt", []),
        f"{name} must enable no-new-privileges",
    )
    require(errors, isinstance(service.get("pids_limit"), int), f"{name} must have a PID limit")


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
            image.startswith("${" + expected_env + ":?"),
            f"{name} image must be supplied by required {expected_env}",
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
    require(errors, bool(ingress.get("ports")), "HTTPS ingress must be the external listener")
    require(errors, not broker.get("ports"), "Spring broker must not publish a host port")
    require(errors, not proxy.get("ports"), "egress proxy must not publish a host port")
    require(errors, broker.get("user") == "10001:10001", "Spring broker must use UID 10001")
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
            str(networks.get("spring-runner-control", {}).get("name", "")).startswith(
                "${ELMOS_SPRING_RUNNER_CONTROL_NETWORK:?"
            ),
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
    rootless = paths.rootless_readme.read_text(encoding="utf-8")
    production = paths.production_readme.read_text(encoding="utf-8")
    runner_environment = paths.runner_environment_example.read_text(encoding="utf-8")
    require(errors, "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=" not in environment, "production env must not contain a single-tenant identity")
    for variable in APPLICATION_SECRET_ENVIRONMENTS + (
        ENGINE_SECRET_ENVIRONMENT,
        ENGINE_REPLAY_ENVIRONMENT,
    ):
        require(errors, f"{variable}=" in environment, f"production env example lacks {variable}")
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
    runner_keys = {
        line.split("=", 1)[0]
        for line in runner_environment.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    require(errors, runner_keys == RUNNER_ENVIRONMENT_ALLOWLIST, "Runner env example key inventory must equal the strict allowlist")
    require(errors, ENGINE_SECRET_ENVIRONMENT not in runner_environment, "Runner env example must exclude the BFF-to-engine HMAC")
    assignments = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in environment.splitlines()
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
    leaked_runner_keys = sorted(runner_only_keys & assignments.keys())
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
    return path


def environment_integer(name: str, environment: Mapping[str, str]) -> int:
    value = environment.get(name, "").strip()
    if not value.isdigit():
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


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
) -> tuple[int, int, str] | None:
    if not path.is_absolute():
        errors.append(f"{label} must be absolute")
        return None
    ancestor_metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            parent_details = parent.lstat()
            if stat.S_ISLNK(parent_details.st_mode):
                errors.append(f"{label} must not traverse symbolic-link parent directories")
                return None
            ancestor_metadata.append((parent, stable_file_metadata(parent_details)))
        details = path.lstat()
    except OSError:
        errors.append(f"{label} is missing")
        return None
    valid = True
    for condition, message in (
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
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
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
        ancestors_unchanged = all(
            not stat.S_ISLNK((current := parent.lstat()).st_mode)
            and stable_file_metadata(current) == before
            for parent, before in ancestor_metadata
        )
        if (
            stable_file_metadata(after) != stable_file_metadata(opened)
            or stable_file_metadata(after_path) != stable_file_metadata(opened)
            or len(contents) != opened.st_size
            or not ancestors_unchanged
        ):
            errors.append(f"{label} or parent path changed while it was being read")
            return None
        if canonical_hmac_secret:
            try:
                decoded = contents.decode("utf-8", errors="strict")
            except UnicodeError:
                errors.append(f"{label} must contain canonical UTF-8 HMAC bytes")
                return None
            if not decoded or decoded[0].isspace() or decoded[-1].isspace():
                errors.append(
                    f"{label} must not have leading or trailing HMAC whitespace"
                )
                return None
        return (opened.st_dev, opened.st_ino, hashlib.sha256(contents).hexdigest())
    except OSError:
        errors.append(f"{label} changed or became unreadable while it was being read")
        return None
    finally:
        os.close(descriptor)


def protected_directory(
    errors: list[str], path: Path, *, label: str, expected_uid: int, expected_gid: int
) -> None:
    if not path.is_absolute() or path == Path("/") or path != Path(os.path.normpath(path)):
        errors.append(f"{label} must be a normalized absolute non-root path")
        return
    try:
        for parent in path.parents:
            parent_details = parent.lstat()
            if not stat.S_ISDIR(parent_details.st_mode) or stat.S_ISLNK(parent_details.st_mode):
                errors.append(
                    f"{label} must not traverse symbolic-link or non-directory parents"
                )
                return
        details = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        errors.append(f"{label} is missing")
        return
    require(errors, not resolved.is_relative_to(ROOT.resolve()), f"{label} must be outside the repository")
    require(errors, stat.S_ISDIR(details.st_mode) and not stat.S_ISLNK(details.st_mode), f"{label} must be a non-symlink directory")
    require(errors, stat.S_IMODE(details.st_mode) == 0o700, f"{label} mode must equal 0700")
    require(errors, details.st_uid == expected_uid, f"{label} owner UID must equal {expected_uid}")
    require(errors, details.st_gid == expected_gid, f"{label} owner GID must equal {expected_gid}")


def ordinary_directory(errors: list[str], path: Path, *, label: str) -> None:
    try:
        details = path.lstat()
    except OSError:
        errors.append(f"{label} is missing")
        return
    require(errors, path.is_absolute(), f"{label} must be absolute")
    require(errors, stat.S_ISDIR(details.st_mode) and not stat.S_ISLNK(details.st_mode), f"{label} must be a non-symlink directory")
    require(errors, details.st_mode & stat.S_IWOTH == 0, f"{label} must not be world-writable")


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


def secure_environment_file_bytes(path: Path) -> tuple[bytes | None, os.stat_result | None, os.stat_result | None, list[str]]:
    """Read an owner-only file without following links or accepting path races."""

    errors: list[str] = []
    if not path.is_absolute():
        return None, None, None, ["Runner environment file path must be absolute"]

    ancestor_metadata: list[tuple[Path, tuple[int, ...]]] = []
    try:
        for parent in path.parents:
            parent_details = parent.lstat()
            if stat.S_ISLNK(parent_details.st_mode):
                return None, None, None, [
                    "Runner environment file must not traverse symbolic-link parent directories"
                ]
            if not stat.S_ISDIR(parent_details.st_mode):
                return None, None, None, [
                    "Runner environment parent path must contain directories only"
                ]
            ancestor_metadata.append((parent, stable_file_metadata(parent_details)))
        details = path.lstat()
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
        if opened_details.st_uid != os.getuid() or opened_details.st_gid != os.getgid():
            errors.append("Runner environment file must be owned by the current user and group")
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
        ancestors_unchanged = True
        for parent, before in ancestor_metadata:
            after_parent = parent.lstat()
            if stat.S_ISLNK(after_parent.st_mode) or stable_file_metadata(after_parent) != before:
                ancestors_unchanged = False
                break
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
) -> tuple[dict[str, str], list[str]]:
    """Parse a Runner env file as inert data and apply allowlisted overrides."""

    errors: list[str] = []
    process_environment = process_environment if process_environment is not None else os.environ
    raw, details, parent_details, read_errors = secure_environment_file_bytes(path)
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

    protected_directory(errors, secret_root, label="broker secret root", expected_uid=rootless_uid, expected_gid=rootless_gid)
    protected_directory(errors, tls_root, label="ingress TLS secret root", expected_uid=rootless_uid, expected_gid=rootless_gid)
    protected_directory(
        errors,
        replay_root,
        label="Spring Runner replay root",
        expected_uid=broker_uid,
        expected_gid=broker_gid,
    )
    require(
        errors,
        replay_root not in {secret_root, tls_root}
        and not replay_root.is_relative_to(secret_root)
        and not replay_root.is_relative_to(tls_root),
        "Spring Runner replay root must be isolated from secret roots",
    )
    secret_records: list[tuple[int, int, str]] = []
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
        )
    except ValueError as error:
        errors.append(str(error))

    try:
        certificate = environment_path("ELMOS_SPRING_INGRESS_TLS_CERT_HOST_PATH", environment)
        details = certificate.lstat()
        require(errors, stat.S_ISREG(details.st_mode) and not stat.S_ISLNK(details.st_mode), "TLS certificate must be a regular non-symlink file")
        require(errors, details.st_size > 0, "TLS certificate must not be empty")
        require(errors, details.st_mode & stat.S_IWOTH == 0, "TLS certificate must not be world-writable")
    except (ValueError, OSError):
        errors.append("Spring ingress TLS certificate is missing or invalid")

    try:
        installed_config = environment_path("ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH", environment)
        require(
            errors,
            installed_config.resolve(strict=True).read_bytes() == paths.ingress_config.read_bytes(),
            "installed Spring ingress config must be byte-identical to the repository contract",
        )
    except (ValueError, OSError):
        errors.append("installed Spring ingress config is missing or invalid")

    try:
        env_file = environment_path("ELMOS_SPRING_RUNNER_ENV_FILE", environment)
        owner_only_file(
            errors,
            env_file,
            label="Spring runner env file",
            expected_uid=rootless_uid,
            expected_gid=rootless_gid,
            maximum_size=65536,
        )
    except ValueError as error:
        errors.append(str(error))

    for name in (
        "ELMOS_SNAPSHOT_ARTIFACT_HOST_PATH",
        "ELMOS_COMMAND_ARTIFACT_HOST_PATH",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
        "ELMOS_VERIFIER_EVIDENCE_HOST_PATH",
    ):
        try:
            ordinary_directory(errors, environment_path(name, environment), label=name)
        except ValueError as error:
            errors.append(str(error))

    try:
        socket_details = socket_path.lstat()
        require(errors, stat.S_ISSOCK(socket_details.st_mode) and not stat.S_ISLNK(socket_details.st_mode), "rootless Docker endpoint must be a Unix socket")
        require(errors, socket_details.st_uid == rootless_uid, "rootless Docker socket owner mismatch")
        require(errors, socket_details.st_mode & 0o007 == 0, "rootless Docker socket must not grant other permissions")
    except OSError:
        errors.append("rootless Docker socket is missing")

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


def compose_container_ids(socket_path: Path, environment: Mapping[str, str]) -> dict[str, str]:
    env_file = environment_path("ELMOS_SPRING_RUNNER_ENV_FILE", environment)
    command = docker_command(
        socket_path,
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(ContractPaths().runner_compose),
        "ps",
        "--format",
        "json",
    )
    rows = command_json(command)
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise TypeError("docker compose ps did not return a JSON list")
    return {
        str(row.get("Service")): str(row.get("ID"))
        for row in rows
        if isinstance(row, dict) and row.get("Service") and row.get("ID")
    }


def validate_running(
    paths: ContractPaths | None = None,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    paths = paths or ContractPaths()
    environment = environment if environment is not None else os.environ
    errors = validate_host(paths, environment)
    try:
        socket_path = environment_path("ELMOS_ROOTLESS_DOCKER_SOCKET", environment)
        identifiers = compose_container_ids(socket_path, environment)
    except (TypeError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        errors.append(str(error))
        return errors
    require(errors, set(identifiers) == EXPECTED_RUNNER_SERVICES, "all three Spring Runner services must be running")
    if set(identifiers) != EXPECTED_RUNNER_SERVICES:
        return errors

    records: dict[str, dict[str, Any]] = {}
    for service, identifier in identifiers.items():
        try:
            inspected = command_json(docker_command(socket_path, "inspect", identifier))
            records[service] = inspected[0]
        except (RuntimeError, json.JSONDecodeError, IndexError, TypeError) as error:
            errors.append(f"{service} inspection failed: {error}")
    if set(records) != EXPECTED_RUNNER_SERVICES:
        return errors

    expected_networks = {
        "spring-runner-ingress": {"elmos-spring-runner-edge", "elmos-spring-runner-broker"},
        "spring-runner-broker": {
            "elmos-spring-runner-broker",
            environment.get("ELMOS_SPRING_RUNNER_CONTROL_NETWORK", ""),
        },
        "spring-runner-egress-proxy": {
            "elmos-spring-runner-broker",
            "elmos-spring-runner-egress",
        },
    }
    for service, record in records.items():
        actual_networks = set(record.get("NetworkSettings", {}).get("Networks", {}))
        require(errors, actual_networks == expected_networks[service], f"{service} runtime network membership drift")
        require(errors, record.get("State", {}).get("Running") is True, f"{service} must be running")
        require(errors, record.get("State", {}).get("Health", {}).get("Status") in {None, "healthy"}, f"{service} healthcheck is not healthy")

    broker_record = records["spring-runner-broker"]
    ingress_record = records["spring-runner-ingress"]
    broker_mounts = {item.get("Destination") for item in broker_record.get("Mounts", [])}
    require(errors, "/run/docker.sock" in broker_mounts, "running Spring broker lacks the rootless socket")
    for service, record in records.items():
        if service != "spring-runner-broker":
            mounts = {item.get("Destination") for item in record.get("Mounts", [])}
            require(errors, "/run/docker.sock" not in mounts, f"{service} must not receive the Docker socket")
    published = ingress_record.get("NetworkSettings", {}).get("Ports", {}).get("8443/tcp")
    require(errors, isinstance(published, list) and len(published) == 1, "HTTPS ingress must publish exactly one 8443 binding")
    broker_ports = broker_record.get("NetworkSettings", {}).get("Ports", {}).get("8082/tcp")
    require(errors, broker_ports is None or broker_ports == [], "Spring broker port must not be published")
    for network_name in ("elmos-spring-runner-edge", "elmos-spring-runner-broker"):
        try:
            inspected = command_json(
                docker_command(socket_path, "network", "inspect", network_name)
            )
            record = inspected[0] if isinstance(inspected, list) and inspected else {}
            require(
                errors,
                record.get("Internal") is True,
                f"running network {network_name} must remain internal/default-deny",
            )
        except (RuntimeError, json.JSONDecodeError) as error:
            errors.append(str(error))
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if (args.check_host or args.check_running) and not args.environment_file:
        return emit(
            ["--check-host and --check-running require --environment-file; shell sourcing is forbidden"],
            mode="ENVIRONMENT_FILE_REQUIRED",
            as_json=args.json,
        )
    environment: Mapping[str, str] = os.environ
    environment_errors: list[str] = []
    if args.environment_file:
        environment, environment_errors = load_environment_file(args.environment_file)
    if environment_errors:
        return emit(environment_errors, mode="ENVIRONMENT_FILE_REJECTED", as_json=args.json)
    if args.check_running:
        return emit(validate_running(environment=environment), mode="RUNNING_HOST_READ_ONLY", as_json=args.json)
    if args.check_host:
        return emit(validate_host(environment=environment), mode="PREPARED_HOST_READ_ONLY", as_json=args.json)
    return emit(validate_static(), mode="STATIC_CONTRACT_ONLY", as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
