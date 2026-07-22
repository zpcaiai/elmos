#!/usr/bin/env python3
"""Validate the production-operability baseline shared by ELMOS HTTP services."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SERVICE_CONFIGS = (
    "apps/agent-gateway/src/main/resources/application.yml",
    "apps/commercial-api/src/main/resources/application.yml",
    "apps/control-plane/src/main/resources/application.yml",
    "apps/enterprise-control/src/main/resources/application.yml",
    "apps/java-engine-worker/src/main/resources/application.yml",
    "apps/workspace-service/src/main/resources/application.yml",
    "engines/ai-platform-engine/src/main/resources/application.yml",
    "engines/database-data-engine/src/main/resources/application.yml",
    "engines/edge-iot-industrial-engine/src/main/resources/application.yml",
    "engines/enterprise-architecture-engine/src/main/resources/application.yml",
    "engines/enterprise-integration-engine/src/main/resources/application.yml",
    "engines/enterprise-suite-engine/src/main/resources/application.yml",
    "engines/infrastructure-engine/src/main/resources/application.yml",
    "engines/mainframe-engine/src/main/resources/application.yml",
    "engines/operations-sre-itsm-engine/src/main/resources/application.yml",
    "engines/security-compliance-engine/src/main/resources/application.yml",
    "engines/software-delivery-platform-engine/src/main/resources/application.yml",
    "engines/test-quality-engine/src/main/resources/application.yml",
)
DATABASE_SERVICES = (
    "apps/control-plane/src/main/resources",
    "apps/workspace-service/src/main/resources",
)
PORT_PATTERN = re.compile(r"^\$\{[A-Z0-9_]+:(\d+)}$")


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML_OBJECT_REQUIRED:{path.relative_to(ROOT)}")
    return loaded


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _value(mapping: dict[str, Any], dotted: str) -> Any:
    current: Any = mapping
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def validate_service_config(relative: str, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        "server.shutdown": "graceful",
        "server.error.include-message": "never",
        "server.error.include-binding-errors": "never",
        "server.error.include-stacktrace": "never",
        "spring.mvc.problemdetails.enabled": True,
        "management.endpoint.health.probes.enabled": True,
        "management.endpoint.health.probes.add-additional-paths": True,
        "management.endpoint.health.show-details": "never",
    }
    for dotted, expected_value in expected.items():
        actual = _value(config, dotted)
        if actual != expected_value:
            errors.append(f"{relative}:{dotted}:expected={expected_value!r}:actual={actual!r}")
    application_name = _value(config, "spring.application.name")
    if not isinstance(application_name, str) or not application_name.startswith("elmos-"):
        errors.append(f"{relative}:spring.application.name:ELMOS_NAME_REQUIRED")
    shutdown_timeout = _value(config, "spring.lifecycle.timeout-per-shutdown-phase")
    if not isinstance(shutdown_timeout, str) or not shutdown_timeout.startswith("${ELMOS_SHUTDOWN_TIMEOUT:"):
        errors.append(f"{relative}:spring.lifecycle.timeout-per-shutdown-phase:EXTERNALIZED_TIMEOUT_REQUIRED")
    exposure = _value(config, "management.endpoints.web.exposure.include")
    exposed = {part.strip() for part in str(exposure or "").split(",") if part.strip()}
    if exposed != {"health", "info"}:
        errors.append(f"{relative}:management.endpoints.web.exposure.include:ONLY_HEALTH_INFO_ALLOWED")
    port = _value(config, "server.port")
    if not isinstance(port, str) or PORT_PATTERN.fullmatch(port) is None:
        errors.append(f"{relative}:server.port:BOUNDED_ENV_DEFAULT_REQUIRED")
    return errors


def validate_prod_database_config(relative_root: str, config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if _value(config, "spring.config.activate.on-profile") != "prod":
        errors.append(f"{relative_root}/application-prod.yml:PROD_PROFILE_REQUIRED")
    for key in ("url", "username", "password"):
        expected = f"${{ELMOS_DATABASE_{'USER' if key == 'username' else key.upper()}}}"
        actual = _value(config, f"spring.datasource.{key}")
        if actual != expected:
            errors.append(
                f"{relative_root}/application-prod.yml:spring.datasource.{key}:"
                "REQUIRED_ENV_WITHOUT_DEFAULT"
            )
    return errors


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    errors: list[str] = []
    artifacts: list[dict[str, Any]] = []
    ports: dict[int, str] = {}
    names: dict[str, str] = {}
    for relative in SERVICE_CONFIGS:
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}:SERVICE_CONFIG_MISSING")
            continue
        artifacts.append(_artifact(path, root))
        config = _load_yaml(path)
        errors.extend(validate_service_config(relative, config))
        port_value = _value(config, "server.port")
        match = PORT_PATTERN.fullmatch(port_value) if isinstance(port_value, str) else None
        if match:
            port = int(match.group(1))
            if port in ports:
                errors.append(f"{relative}:DEFAULT_PORT_COLLISION:{port}:{ports[port]}")
            ports[port] = relative
        name = _value(config, "spring.application.name")
        if isinstance(name, str):
            if name in names:
                errors.append(f"{relative}:APPLICATION_NAME_COLLISION:{name}:{names[name]}")
            names[name] = relative
    for relative_root in DATABASE_SERVICES:
        prod_path = root / relative_root / "application-prod.yml"
        if not prod_path.is_file():
            errors.append(f"{relative_root}/application-prod.yml:PROD_CONFIG_MISSING")
            continue
        artifacts.append(_artifact(prod_path, root))
        errors.extend(validate_prod_database_config(relative_root, _load_yaml(prod_path)))
    return {
        "status": "PASS" if not errors else "FAIL",
        "service_count": len(SERVICE_CONFIGS),
        "database_service_count": len(DATABASE_SERVICES),
        "unique_application_names": len(names),
        "unique_default_ports": len(ports),
        "checks": {
            "graceful_shutdown": True,
            "safe_error_responses": True,
            "liveness_readiness_probes": True,
            "externalized_shutdown_timeout": True,
            "production_database_fail_closed": True,
        },
        "external_evidence_status": "NOT_RUN",
        "engineering_evidence_only": True,
        "config_artifacts": sorted(artifacts, key=lambda item: item["path"]),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate_repository(args.root.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
