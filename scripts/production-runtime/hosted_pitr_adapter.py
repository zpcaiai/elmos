#!/usr/bin/env python3
"""Typed command and endpoint contracts for hosted PostgreSQL PITR drills."""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime
from typing import Any


SUPPORTED_PITR_DRIVERS = {
    "aws-rds-postgresql-v1",
    "gcp-cloudsql-postgresql-v1",
    "azure-postgresql-flexible-v1",
}
SAFE_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")


class PitrAdapterError(ValueError):
    pass


def validate_pitr_binding(binding: dict[str, Any]) -> None:
    driver = binding.get("driver")
    if isinstance(driver, str) and driver.startswith("REQUIRED"):
        return
    if driver not in SUPPORTED_PITR_DRIVERS:
        raise PitrAdapterError(f"unsupported PITR driver: {driver}")
    common = (
        "source_instance",
        "restore_target",
        "restore_database",
        "restore_username_env",
        "restore_password_env",
        "source_database_url_env",
        "marker_tenant_id",
        "marker_id",
        "marker_sha256",
    )
    for field in common:
        if not isinstance(binding.get(field), str) or not binding[field]:
            raise PitrAdapterError(f"PITR binding requires {field}")
    for field in ("source_instance", "restore_target", "restore_database"):
        if not SAFE_RESOURCE.fullmatch(binding[field]):
            raise PitrAdapterError(f"PITR {field} contains unsafe characters")
    try:
        import uuid

        uuid.UUID(binding["marker_tenant_id"])
        uuid.UUID(binding["marker_id"])
    except ValueError as exc:
        raise PitrAdapterError("PITR marker tenant and id must be UUIDs") from exc
    if not re.fullmatch(r"[0-9a-f]{64}", binding["marker_sha256"]):
        raise PitrAdapterError("PITR marker_sha256 must be lowercase SHA-256")
    delay = binding.get("archive_delay_seconds")
    if not isinstance(delay, int) or not 30 <= delay <= 3600:
        raise PitrAdapterError("PITR archive_delay_seconds must be between 30 and 3600")
    if not isinstance(binding.get("cleanup_after_verification"), bool):
        raise PitrAdapterError("PITR cleanup_after_verification must be boolean")
    if driver == "aws-rds-postgresql-v1":
        require(binding, "region")
    elif driver == "gcp-cloudsql-postgresql-v1":
        require(binding, "project")
    else:
        require(binding, "subscription")
        require(binding, "resource_group")


def require(binding: dict[str, Any], field: str) -> str:
    value = binding.get(field)
    if not isinstance(value, str) or not SAFE_RESOURCE.fullmatch(value):
        raise PitrAdapterError(f"PITR binding requires safe {field}")
    return value


def restore_command(binding: dict[str, Any], restore_time: str) -> list[str]:
    validate_pitr_binding(binding)
    # Parse first so a locale-dependent or timezone-free timestamp can never be
    # sent to a cloud control plane.
    parsed = datetime.fromisoformat(restore_time.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise PitrAdapterError("PITR restore_time must include a timezone")
    driver = binding["driver"]
    if driver == "aws-rds-postgresql-v1":
        return [
            "aws", "rds", "restore-db-instance-to-point-in-time",
            "--source-db-instance-identifier", binding["source_instance"],
            "--target-db-instance-identifier", binding["restore_target"],
            "--restore-time", restore_time,
            "--region", binding["region"],
            "--no-publicly-accessible",
            "--tags", "Key=elmos-purpose,Value=pitr-verification",
        ]
    if driver == "gcp-cloudsql-postgresql-v1":
        return [
            "gcloud", "sql", "instances", "clone",
            binding["source_instance"], binding["restore_target"],
            f"--point-in-time={restore_time}",
            f"--project={binding['project']}", "--quiet",
        ]
    return [
        "az", "postgres", "flexible-server", "restore",
        "--subscription", binding["subscription"],
        "--resource-group", binding["resource_group"],
        "--name", binding["restore_target"],
        "--source-server", binding["source_instance"],
        "--restore-time", restore_time,
        "--output", "json",
    ]


def wait_command(binding: dict[str, Any]) -> list[str] | None:
    driver = binding["driver"]
    if driver == "aws-rds-postgresql-v1":
        return [
            "aws", "rds", "wait", "db-instance-available",
            "--db-instance-identifier", binding["restore_target"],
            "--region", binding["region"],
        ]
    # gcloud clone and az restore are synchronous unless explicitly passed
    # --async/--no-wait, which this adapter never does.
    return None


def describe_command(binding: dict[str, Any]) -> list[str]:
    driver = binding["driver"]
    if driver == "aws-rds-postgresql-v1":
        return [
            "aws", "rds", "describe-db-instances",
            "--db-instance-identifier", binding["restore_target"],
            "--region", binding["region"], "--output", "json",
        ]
    if driver == "gcp-cloudsql-postgresql-v1":
        return [
            "gcloud", "sql", "instances", "describe",
            binding["restore_target"], f"--project={binding['project']}",
            "--format=json",
        ]
    return [
        "az", "postgres", "flexible-server", "show",
        "--subscription", binding["subscription"],
        "--resource-group", binding["resource_group"],
        "--name", binding["restore_target"], "--output", "json",
    ]


def restored_endpoint(binding: dict[str, Any], describe_output: str) -> tuple[str, int]:
    try:
        value = json.loads(describe_output)
    except json.JSONDecodeError as exc:
        raise PitrAdapterError("PITR provider describe output is not JSON") from exc
    driver = binding["driver"]
    if driver == "aws-rds-postgresql-v1":
        instances = value.get("DBInstances") if isinstance(value, dict) else None
        endpoint = instances[0].get("Endpoint") if isinstance(instances, list) and instances else None
        host = endpoint.get("Address") if isinstance(endpoint, dict) else None
        port = endpoint.get("Port", 5432) if isinstance(endpoint, dict) else 5432
    elif driver == "gcp-cloudsql-postgresql-v1":
        addresses = value.get("ipAddresses") if isinstance(value, dict) else None
        selected = next(
            (item for item in addresses or [] if item.get("type") in {"PRIVATE", "PRIMARY"}),
            None,
        )
        host = selected.get("ipAddress") if isinstance(selected, dict) else None
        port = 5432
    else:
        host = value.get("fullyQualifiedDomainName") if isinstance(value, dict) else None
        port = 5432
    if not isinstance(host, str) or not host or not isinstance(port, int):
        raise PitrAdapterError("PITR restored endpoint is missing")
    if any(character.isspace() for character in host) or "/" in host:
        raise PitrAdapterError("PITR restored endpoint host is malformed")
    try:
        # Valid IPs are accepted; DNS names receive a conservative character check.
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
            raise PitrAdapterError("PITR restored endpoint DNS name is malformed")
    if not 1 <= port <= 65535:
        raise PitrAdapterError("PITR restored endpoint port is invalid")
    return host, port


def cleanup_command(binding: dict[str, Any]) -> list[str]:
    driver = binding["driver"]
    if driver == "aws-rds-postgresql-v1":
        return [
            "aws", "rds", "delete-db-instance",
            "--db-instance-identifier", binding["restore_target"],
            "--region", binding["region"], "--skip-final-snapshot",
            "--delete-automated-backups",
        ]
    if driver == "gcp-cloudsql-postgresql-v1":
        return [
            "gcloud", "sql", "instances", "delete",
            binding["restore_target"], f"--project={binding['project']}", "--quiet",
        ]
    return [
        "az", "postgres", "flexible-server", "delete",
        "--subscription", binding["subscription"],
        "--resource-group", binding["resource_group"],
        "--name", binding["restore_target"], "--yes",
    ]
