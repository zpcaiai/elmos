"""Fail-closed Control Plane and independently attested Runner probes."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .contracts import (
    ContractError,
    parse_timestamp,
    require_mapping,
    require_string,
    sha256_payload,
)


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_DIGEST_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


def _secure_url(value: str, field_name: str) -> str:
    raw = require_string(value, field_name).rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ContractError("runtime_url", f"{field_name} must be an HTTP(S) URL without credentials")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ContractError("runtime_tls", f"{field_name} must use HTTPS outside loopback")
    return raw


def validate_runtime_plan(value: Any) -> Mapping[str, Any]:
    plan = require_mapping(value, "runtime_plan")
    if plan.get("schema_version") != 1:
        raise ContractError("runtime_plan_schema", "runtime plan schema_version must be 1")
    require_string(plan.get("gate_id"), "runtime_plan.gate_id")
    control = require_mapping(plan.get("control_plane"), "runtime_plan.control_plane")
    runner = require_mapping(plan.get("runner"), "runtime_plan.runner")
    for field_name in ("base_url_env", "operations_key_env", "tenant_env", "actor_env"):
        if not _ENV_NAME.fullmatch(require_string(control.get(field_name), f"control_plane.{field_name}")):
            raise ContractError("runtime_env_name", f"control_plane.{field_name} is invalid")
    for field_name in (
        "node_id_env",
        "pool_id_env",
        "capabilities_env",
        "agent_version_env",
        "agent_image_env",
        "workload_image_env",
        "allowlist_version_env",
    ):
        if not _ENV_NAME.fullmatch(require_string(runner.get(field_name), f"runner.{field_name}")):
            raise ContractError("runtime_env_name", f"runner.{field_name} is invalid")
    for field_name in ("readiness_path", "liveness_path", "reaper_path", "runner_inventory_path"):
        path = require_string(control.get(field_name), f"control_plane.{field_name}")
        if not path.startswith("/") or ".." in path or "//" in path:
            raise ContractError("runtime_path", f"control_plane.{field_name} is invalid")
    maximum_age = runner.get("max_heartbeat_age_seconds")
    if isinstance(maximum_age, bool) or not isinstance(maximum_age, int) or not 30 <= maximum_age <= 900:
        raise ContractError("heartbeat_age", "max_heartbeat_age_seconds must be between 30 and 900")
    if runner.get("required_status") != "READY" or runner.get("attestation_required") is not True:
        raise ContractError("runner_gate", "runtime plan must require READY and verified attestation")
    ack_env = require_string(plan.get("execution_ack_env"), "runtime_plan.execution_ack_env")
    if not _ENV_NAME.fullmatch(ack_env):
        raise ContractError("runtime_env_name", "execution_ack_env is invalid")
    if plan.get("external_evidence") != "NOT_RUN" or plan.get("production_certification") != "NOT_CERTIFIED":
        raise ContractError("predeclared_runtime_result", "runtime plan cannot predeclare external success")
    return plan


def runtime_preflight(
    plan_value: Any,
    *,
    environment: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    plan = validate_runtime_plan(plan_value)
    values = os.environ if environment is None else environment
    control = require_mapping(plan["control_plane"], "control_plane")
    runner = require_mapping(plan["runner"], "runner")
    required_names = [control[field] for field in ("base_url_env", "operations_key_env", "tenant_env", "actor_env")]
    required_names.extend(
        runner[field]
        for field in (
            "node_id_env",
            "pool_id_env",
            "capabilities_env",
            "agent_version_env",
            "agent_image_env",
            "workload_image_env",
            "allowlist_version_env",
        )
    )
    blockers = [f"missing_environment:{name}" for name in required_names if not values.get(name, "").strip()]
    if not blockers:
        try:
            _secure_url(values[control["base_url_env"]], control["base_url_env"])
            for name in (runner["node_id_env"], runner["pool_id_env"], runner["allowlist_version_env"]):
                if not _IDENTITY.fullmatch(values[name].strip()):
                    raise ContractError("runtime_identity", f"{name} has an invalid identity")
            capabilities = [item.strip() for item in values[runner["capabilities_env"]].split(",") if item.strip()]
            if not capabilities or len(capabilities) > 32 or any(not _IDENTITY.fullmatch(item) for item in capabilities):
                raise ContractError("runner_capabilities", "ELMOS_RUNNER_CAPABILITIES is invalid")
            if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", values[runner["agent_version_env"]].strip()):
                raise ContractError("runner_agent_version", "Runner agent version must be exact")
            for image_field in ("agent_image_env", "workload_image_env"):
                if not _DIGEST_IMAGE.fullmatch(values[runner[image_field]].strip()):
                    raise ContractError("runner_image", f"{runner[image_field]} must be digest-pinned")
        except ContractError as exc:
            blockers.append(f"{exc.code}:{exc}")
    return {
        "status": "BLOCKED" if blockers else "READY",
        "control_plane": "NOT_RUN",
        "runner": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "blockers": blockers,
    }


def _response_body(response: Any, field_name: str) -> Mapping[str, Any]:
    try:
        response.raise_for_status()
        return require_mapping(response.json(), field_name)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("runtime_probe_unknown", f"{field_name} returned an unknown result") from exc


def _get(client: Any, path: str, field_name: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
    try:
        response = client.get(path, **({"headers": headers} if headers is not None else {}))
    except Exception as exc:
        raise ContractError("runtime_probe_unknown", f"{field_name} request result is unknown") from exc
    return _response_body(response, field_name)


def probe_production_runtime(
    plan_value: Any,
    *,
    environment: Mapping[str, str] | None = None,
    client: Any | None = None,
    now: datetime | None = None,
) -> Mapping[str, Any]:
    plan = validate_runtime_plan(plan_value)
    values = os.environ if environment is None else environment
    preflight = runtime_preflight(plan, environment=values)
    if preflight["status"] != "READY":
        raise ContractError("runtime_not_configured", "runtime preflight is blocked")
    if values.get(plan["execution_ack_env"], "").strip() != plan["gate_id"]:
        raise ContractError("runtime_probe_not_acknowledged", "runtime probe acknowledgment does not match gate_id")

    control = require_mapping(plan["control_plane"], "control_plane")
    runner = require_mapping(plan["runner"], "runner")
    base_url = _secure_url(values[control["base_url_env"]], control["base_url_env"])
    if client is None:
        try:
            import httpx
        except ImportError as exc:
            raise ContractError("runtime_client_not_configured", "install the integrations extra") from exc
        client = httpx.Client(base_url=base_url, timeout=10.0, follow_redirects=False)

    readiness = _get(client, control["readiness_path"], "control_plane.readiness")
    liveness = _get(client, control["liveness_path"], "control_plane.liveness")
    reaper = _get(client, control["reaper_path"], "control_plane.reaper")
    if readiness.get("status") != "UP" or liveness.get("status") != "UP":
        raise ContractError("control_plane_not_ready", "Control Plane liveness/readiness is not UP")
    parse_timestamp(reaper.get("checkedAt"), "control_plane.reaper.checkedAt")

    headers = {
        "X-ELMOS-Operations-Key": values[control["operations_key_env"]],
        "X-ELMOS-Organization-ID": values[control["tenant_env"]],
        "X-ELMOS-Actor-ID": values[control["actor_env"]],
        "X-ELMOS-Admin-Role": "VIEWER",
    }
    inventory = _get(
        client,
        control["runner_inventory_path"],
        "control_plane.runner_inventory",
        headers=headers,
    )
    items = inventory.get("items")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, bytearray)):
        raise ContractError("runner_inventory", "Runner inventory items must be an array")
    node_id = values[runner["node_id_env"]].strip()
    pool_id = values[runner["pool_id_env"]].strip()
    matches = [
        require_mapping(item, "runner_inventory.item")
        for item in items
        if isinstance(item, Mapping) and item.get("runnerNodeId") == node_id
    ]
    if len(matches) != 1:
        raise ContractError("runner_identity", "exactly one expected Runner node must be visible")
    node = matches[0]
    expected_capabilities = {item.strip() for item in values[runner["capabilities_env"]].split(",") if item.strip()}
    raw_capabilities = node.get("capabilities", ())
    if not isinstance(raw_capabilities, Sequence) or isinstance(raw_capabilities, (str, bytes, bytearray)):
        raise ContractError("runner_capabilities", "Runner capabilities must be an array")
    observed_capabilities = set(raw_capabilities)
    if any(not isinstance(item, str) for item in observed_capabilities):
        raise ContractError("runner_capabilities", "Runner capabilities must contain strings")
    if (
        node.get("runnerPoolId") != pool_id
        or node.get("agentVersion") != values[runner["agent_version_env"]].strip()
        or node.get("fleetStatus") != runner["required_status"]
        or node.get("attestationVerified") is not True
        or not expected_capabilities.issubset(observed_capabilities)
        or node.get("imageAllowlistVersion") != values[runner["allowlist_version_env"]].strip()
    ):
        raise ContractError("runner_not_ready", "Runner identity, pool, capability, allowlist, status, or attestation is invalid")
    heartbeat = parse_timestamp(node.get("lastHeartbeatAt"), "runner.lastHeartbeatAt")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    heartbeat_age = (current - heartbeat).total_seconds()
    if heartbeat_age < 0 or heartbeat_age > runner["max_heartbeat_age_seconds"]:
        raise ContractError("runner_heartbeat_stale", "Runner heartbeat is stale or future-dated")

    safe_inventory = {
        "runnerNodeId": node_id,
        "runnerPoolId": pool_id,
        "agentVersion": node["agentVersion"],
        "fleetStatus": node["fleetStatus"],
        "capabilities": sorted(observed_capabilities),
        "attestationVerified": True,
        "imageAllowlistVersion": node["imageAllowlistVersion"],
        "lastHeartbeatAt": node["lastHeartbeatAt"],
    }
    return {
        "schema_version": 1,
        "status": "EXECUTED_UNVERIFIED",
        "control_plane": {
            "status": "UP",
            "base_url_digest": sha256_payload(base_url),
            "readiness_digest": sha256_payload(readiness),
            "liveness_digest": sha256_payload(liveness),
            "reaper_digest": sha256_payload(reaper),
        },
        "runner": {
            "status": "READY",
            "inventory": safe_inventory,
            "inventory_digest": sha256_payload(inventory),
            "heartbeat_age_seconds": round(heartbeat_age, 3),
            "configured_agent_image_digest": sha256_payload(values[runner["agent_image_env"]].strip()),
            "configured_workload_image_digest": sha256_payload(values[runner["workload_image_env"]].strip()),
            "image_observation": "CONFIGURATION_BOUND_NOT_RUNTIME_OBSERVED",
        },
        "external_evidence": "EXECUTED_UNVERIFIED",
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
    }
