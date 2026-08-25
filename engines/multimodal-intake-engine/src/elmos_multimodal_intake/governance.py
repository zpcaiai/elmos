"""Provider routing, durable-state, and retention governance operations."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .canonical import require_idempotency_key
from .errors import ValidationError
from .models import TenantContext
from .store import IntakeStore

if TYPE_CHECKING:
    from .skill_runtime import RuntimeContext


class GovernanceContractError(ValueError):
    """Raised when a policy-sensitive operation lacks required facts."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inputs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    value = request.get("inputs")
    if not isinstance(value, Mapping):
        raise GovernanceContractError("inputs must be an object")
    return value


def _runtime_namespace(
    request: Mapping[str, Any], container: str, namespace: str
) -> Mapping[str, Any] | None:
    """Return authority-bearing facts only from the runtime envelope."""

    root = request.get(container)
    if not isinstance(root, Mapping):
        return None
    value = root.get(namespace)
    return value if isinstance(value, Mapping) else None


def _scope_matches(value: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    return (
        value.get("tenant_id") == request.get("tenant_id")
        and value.get("project_id") == request.get("project_id")
    )


def _string_set(value: Any, field: str, *, maximum: int = 10_000) -> set[str]:
    items = _sequence(value, field, maximum=maximum)
    normalized: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            raise GovernanceContractError(f"{field}[{index}] must be a non-blank string")
        normalized.add(item.strip())
    return normalized


def _finite_float(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise GovernanceContractError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceContractError(f"{field} must be a finite number") from exc
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise GovernanceContractError(f"{field} must be finite and at least {minimum}")
    return number


def _sha256_identity(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value) is not None


def _sequence(value: Any, field: str, *, maximum: int = 100_000) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise GovernanceContractError(f"{field} must be an array")
    if len(value) > maximum:
        raise GovernanceContractError(f"{field} exceeds the bounded item limit")
    return list(value)


def route_provider(request: Mapping[str, Any]) -> dict[str, Any]:
    """Choose one policy-compliant provider without privacy-weakening fallback."""

    values = _inputs(request)
    routing_policy = _runtime_namespace(request, "policy", "provider_routing")
    registry = _runtime_namespace(request, "capabilities", "provider_registry")
    if (
        routing_policy is None
        or not str(routing_policy.get("version", "")).strip()
        or not _scope_matches(routing_policy, request)
    ):
        return {
            "state": "BLOCKED",
            "code": "PROVIDER_ROUTING_POLICY_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN", "rejected": []},
        }
    if registry is None or not str(registry.get("version", "")).strip():
        return {
            "state": "BLOCKED",
            "code": "PROVIDER_CAPABILITY_REGISTRY_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN", "rejected": []},
        }
    providers = _sequence(
        registry.get("providers", []),
        "capabilities.provider_registry.providers",
        maximum=1_000,
    )
    modality = str(values.get("modality", "text"))
    data_classification = str(routing_policy.get("data_classification", "")).upper()
    if data_classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "SECRET", "RESTRICTED"}:
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_DATA_CLASSIFICATION_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN", "rejected": []},
        }
    requested_classification = values.get("data_classification")
    if requested_classification is not None and str(requested_classification).upper() != data_classification:
        return {
            "state": "BLOCKED",
            "code": "DATA_CLASSIFICATION_POLICY_MISMATCH",
            "outputs": {"decision": "NO_ROUTE", "rejected": []},
        }
    required_region = routing_policy.get("required_region")
    asset_id = str(values.get("asset_id", "")).strip()
    consented_assets = _string_set(
        routing_policy.get("external_provider_consent_asset_ids", []),
        "policy.provider_routing.external_provider_consent_asset_ids",
    )
    external_consent = (
        routing_policy.get("external_provider_consent") is True
        and bool(asset_id)
        and asset_id in consented_assets
    )
    allowlist = _string_set(
        routing_policy.get("provider_allowlist", []),
        "policy.provider_routing.provider_allowlist",
    )
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for index, raw in enumerate(providers):
        if not isinstance(raw, Mapping):
            raise GovernanceContractError(
                f"capabilities.provider_registry.providers[{index}] must be an object"
            )
        provider_id = str(raw.get("provider_id", ""))
        if not provider_id:
            raise GovernanceContractError("provider_id is required")
        modalities = _string_set(
            raw.get("modalities", []),
            f"capabilities.provider_registry.providers[{index}].modalities",
        )
        reason: str | None = None
        if provider_id not in allowlist:
            reason = "NOT_ALLOWLISTED"
        elif modality not in modalities:
            reason = "MODALITY_UNSUPPORTED"
        elif str(raw.get("health", "UNKNOWN")) not in {"HEALTHY", "DEGRADED"}:
            reason = "PROVIDER_UNAVAILABLE"
        elif int(raw.get("attempts", 0)) >= int(raw.get("max_attempts", 2)):
            reason = "RETRY_BUDGET_EXHAUSTED"
        elif required_region and str(raw.get("region")) != str(required_region):
            reason = "REGION_POLICY_MISMATCH"
        elif bool(raw.get("external", True)) and not external_consent:
            reason = "EXTERNAL_PROVIDER_NOT_AUTHORIZED"
        elif data_classification in {"SECRET", "RESTRICTED"} and not bool(raw.get("approved_for_restricted", False)):
            reason = "DATA_CLASSIFICATION_FORBIDDEN"
        if reason:
            rejected.append({"provider_id": provider_id, "reason": reason})
            continue
        quality_score = _finite_float(
            raw.get("quality_score", 0.0), "provider.quality_score", minimum=0.0
        )
        if quality_score > 1.0:
            raise GovernanceContractError("provider.quality_score must not exceed 1")
        candidates.append(
            {
                "provider_id": provider_id,
                "provider_version": str(raw.get("provider_version", "unknown")),
                "region": raw.get("region"),
                "cost_per_unit": _finite_float(raw.get("cost_per_unit", 0.0), "provider.cost_per_unit", minimum=0.0),
                "latency_p95_ms": _finite_float(raw.get("latency_p95_ms", 1_000_000.0), "provider.latency_p95_ms", minimum=0.0),
                "quality_score": quality_score,
                "health": raw.get("health"),
            }
        )
    candidates.sort(key=lambda item: (-item["quality_score"], item["cost_per_unit"], item["latency_p95_ms"], item["provider_id"]))
    if not candidates:
        return {
            "state": "BLOCKED",
            "code": "PROVIDER_ROUTE_UNAVAILABLE",
            "outputs": {"decision": "NO_ROUTE", "rejected": rejected, "unbounded_retry": False},
        }
    selected = candidates[0]
    decision = {
        "decision": "ROUTE",
        "selected": selected,
        "rejected": rejected,
        "parameters_digest": _digest(values.get("parameters", {})),
        "policy_version": str(routing_policy["version"]),
        "provider_registry_version": str(registry["version"]),
        "data_classification": data_classification,
    }
    decision["routing_digest"] = _digest(decision)
    return {"state": "SUCCEEDED", "code": "PROVIDER_ROUTE_SELECTED", "outputs": decision}


_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"RUNNING", "CANCELLED"}),
    "RUNNING": frozenset({"PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"}),
    "PAUSED": frozenset({"RUNNING", "CANCELLED"}),
    "FAILED_RETRYABLE": frozenset({"RUNNING", "FAILED_FINAL", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "FAILED_FINAL": frozenset(),
    "CANCELLED": frozenset(),
}


def process_durable_transition(request: Mapping[str, Any]) -> dict[str, Any]:
    """Apply a durable transition with idempotency and effect reconciliation."""

    values = _inputs(request)
    durable_state = _runtime_namespace(request, "capabilities", "durable_state")
    if (
        durable_state is None
        or not str(durable_state.get("version", "")).strip()
        or not _scope_matches(durable_state, request)
    ):
        return {
            "state": "BLOCKED",
            "code": "DURABLE_STATE_CAPABILITY_UNAVAILABLE",
            "outputs": {"transition_state": "NOT_RUN"},
        }
    current = str(durable_state.get("current_state", "")).upper()
    target = str(values.get("target_state", "RUNNING")).upper()
    if current not in _TRANSITIONS or target not in _TRANSITIONS:
        raise GovernanceContractError("durable processing state is invalid")
    idempotency_key = str(request.get("idempotency_key", ""))
    if not idempotency_key:
        return {"state": "BLOCKED", "code": "IDEMPOTENCY_KEY_REQUIRED", "outputs": {"current_state": current}}
    requested_current = values.get("current_state")
    if requested_current is not None and str(requested_current).upper() != current:
        return {
            "state": "BLOCKED",
            "code": "DURABLE_STATE_MISMATCH",
            "outputs": {"authoritative_state": current},
        }
    task_id = str(values.get("task_id", ""))
    if not task_id:
        raise GovernanceContractError("task_id is required")
    payload = values.get("payload", {})
    if not isinstance(payload, Mapping):
        raise GovernanceContractError("inputs.payload must be an object")
    binding = {
        "tenant_id": request.get("tenant_id"),
        "project_id": request.get("project_id"),
        "skill": "elmos-durable-processing-and-recovery",
        "idempotency_key": idempotency_key,
        "task_id": task_id,
        "target_state": target,
        "payload_digest": _digest(dict(payload)),
    }
    binding_digest = _digest(binding)
    prior_events = _sequence(
        durable_state.get("prior_events", []),
        "capabilities.durable_state.prior_events",
    )
    matching = [item for item in prior_events if isinstance(item, Mapping) and item.get("idempotency_key") == idempotency_key]
    if matching:
        conflicting = next(
            (
                prior
                for prior in matching
                if prior.get("target_state") != target
                or prior.get("idempotency_binding_digest") != binding_digest
                or prior.get("tenant_id") != binding["tenant_id"]
                or prior.get("project_id") != binding["project_id"]
                or prior.get("skill") != binding["skill"]
                or prior.get("task_id") != binding["task_id"]
                or prior.get("payload_digest") != binding["payload_digest"]
            ),
            None,
        )
        if conflicting is not None:
            return {
                "state": "BLOCKED",
                "code": "IDEMPOTENCY_KEY_CONFLICT",
                "outputs": {"prior_event": dict(conflicting)},
            }
        prior = matching[-1]
        return {"state": "SUCCEEDED", "code": "DURABLE_TRANSITION_REPLAYED", "outputs": {"event": prior, "duplicate_effects": 0}}
    if target not in _TRANSITIONS[current]:
        return {"state": "BLOCKED", "code": "INVALID_DURABLE_STATE_TRANSITION", "outputs": {"current_state": current, "target_state": target}}
    attempted_receipts = _string_set(
        durable_state.get("attempted_effect_receipts", []),
        "capabilities.durable_state.attempted_effect_receipts",
    )
    recorded_receipts = _string_set(
        durable_state.get("recorded_effect_receipts", []),
        "capabilities.durable_state.recorded_effect_receipts",
    )
    event = {
        "tenant_id": request.get("tenant_id"),
        "project_id": request.get("project_id"),
        "skill": "elmos-durable-processing-and-recovery",
        "actor_id": request.get("actor_id"),
        "task_id": task_id,
        "from_state": current,
        "target_state": target,
        "idempotency_key": idempotency_key,
        "idempotency_binding_digest": binding_digest,
        "payload_digest": binding["payload_digest"],
        "checkpoint_digest": values.get("checkpoint_digest"),
        "durable_state_version": str(durable_state["version"]),
        "effects_to_skip": sorted(attempted_receipts & recorded_receipts),
        "effects_to_reconcile": sorted(attempted_receipts - recorded_receipts),
    }
    if event["checkpoint_digest"] is not None and not _sha256_identity(event["checkpoint_digest"]):
        raise GovernanceContractError("checkpoint_digest must be sha256 content identity")
    event["event_id"] = "event_" + _digest(event)[7:31]
    return {
        "state": "SUCCEEDED",
        "code": "DURABLE_TRANSITION_RECORDED",
        "outputs": {"event": event, "authoritative_state": target, "client_connection_controls_task": False},
    }


def apply_retention_governance(request: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate retention/delete/export without fabricating deletion completion."""

    values = _inputs(request)
    action = str(values.get("action", "evaluate")).lower()
    policy = _runtime_namespace(request, "policy", "retention")
    if policy is None or not _scope_matches(policy, request):
        return {
            "state": "BLOCKED",
            "code": "RETENTION_POLICY_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN"},
        }
    policy_version = str(policy.get("version", ""))
    if not policy_version:
        return {
            "state": "BLOCKED",
            "code": "RETENTION_POLICY_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN"},
        }
    allowed_actions = _string_set(
        policy.get("allowed_actions", []), "policy.retention.allowed_actions"
    )
    if action not in allowed_actions:
        return {
            "state": "BLOCKED",
            "code": "RETENTION_ACTION_NOT_AUTHORIZED",
            "outputs": {"action": action, "policy_version": policy_version},
        }
    if action == "provider-access":
        asset_id = str(values.get("asset_id", "")).strip()
        consented_assets = _string_set(
            policy.get("third_party_provider_consent_asset_ids", []),
            "policy.retention.third_party_provider_consent_asset_ids",
        )
        approved = (
            policy.get("allow_third_party_provider") is True
            and policy.get("asset_provider_consent") is True
            and bool(asset_id)
            and asset_id in consented_assets
        )
        return {
            "state": "SUCCEEDED" if approved else "BLOCKED",
            "code": "PROVIDER_ACCESS_ALLOWED" if approved else "PROVIDER_ACCESS_DENIED",
            "outputs": {"allowed": approved, "policy_version": policy_version},
        }
    inventory = _runtime_namespace(request, "capabilities", "governance_inventory")
    if inventory is None or inventory.get("complete") is not True:
        return {
            "state": "BLOCKED",
            "code": "GOVERNANCE_INVENTORY_UNAVAILABLE",
            "outputs": {"decision": "NOT_RUN", "policy_version": policy_version},
        }
    inventory_version = str(inventory.get("version", ""))
    objects = _sequence(
        inventory.get("objects", []),
        "capabilities.governance_inventory.objects",
    )
    if not inventory_version or not objects:
        return {
            "state": "BLOCKED",
            "code": "GOVERNANCE_INVENTORY_EMPTY",
            "outputs": {"decision": "NOT_RUN", "policy_version": policy_version},
        }
    scoped: list[dict[str, Any]] = []
    for index, item in enumerate(objects):
        if not isinstance(item, Mapping):
            raise GovernanceContractError(
                f"capabilities.governance_inventory.objects[{index}] must be an object"
            )
        if (
            item.get("tenant_id") != request.get("tenant_id")
            or item.get("project_id") != request.get("project_id")
        ):
            return {
                "state": "BLOCKED",
                "code": "GOVERNANCE_INVENTORY_SCOPE_MISMATCH",
                "outputs": {"decision": "NOT_RUN", "policy_version": policy_version},
            }
        if not str(item.get("object_id", "")).strip() or not str(item.get("store", "")).strip():
            raise GovernanceContractError("governance inventory objects require object_id and store")
        scoped.append(dict(item))
    inventory_body = {
        "tenant_id": request.get("tenant_id"),
        "project_id": request.get("project_id"),
        "version": inventory_version,
        "complete": True,
        "objects": scoped,
    }
    if inventory.get("inventory_digest") != _digest(inventory_body):
        return {
            "state": "BLOCKED",
            "code": "GOVERNANCE_INVENTORY_INTEGRITY_FAILED",
            "outputs": {"decision": "NOT_RUN", "policy_version": policy_version},
        }
    if action == "delete":
        held = [item for item in scoped if bool(item.get("retention_hold", False))]
        if held:
            return {
                "state": "BLOCKED",
                "code": "RETENTION_HOLD_BLOCKS_DELETION",
                "outputs": {"held_object_ids": sorted(str(item.get("object_id")) for item in held), "policy_version": policy_version},
            }
        return {
            "state": "BLOCKED",
            "code": "DURABLE_DELETION_WORKFLOW_REQUIRED",
            "outputs": {
                "decision": "NOT_RUN",
                "policy_version": policy_version,
                "inventory_version": inventory_version,
                "inventory_digest": inventory["inventory_digest"],
                "host_deletion_flags_accepted_as_proof": False,
                "completed": False,
            },
        }
    if action == "export":
        export = {
            "tenant_id": request.get("tenant_id"),
            "project_id": request.get("project_id"),
            "object_refs": sorted({str(item.get("object_id")) for item in scoped}),
            "policy_version": policy_version,
            "inventory_version": inventory_version,
            "inventory_digest": inventory["inventory_digest"],
            "content_in_audit_log": False,
        }
        export["export_digest"] = _digest(export)
        return {"state": "SUCCEEDED", "code": "GOVERNED_EXPORT_PREPARED", "outputs": export}
    if action != "evaluate":
        raise GovernanceContractError("governance action must be evaluate, provider-access, delete, or export")
    retention_days = int(policy.get("retention_days", 0))
    if retention_days <= 0:
        return {
            "state": "BLOCKED",
            "code": "RETENTION_PERIOD_INVALID",
            "outputs": {"policy_version": policy_version},
        }
    return {
        "state": "SUCCEEDED",
        "code": "RETENTION_POLICY_EVALUATED",
        "outputs": {
            "policy_version": policy_version,
            "inventory_version": inventory_version,
            "inventory_digest": inventory["inventory_digest"],
            "retention_days": retention_days,
            "object_count": len(scoped),
        },
    }


class GovernanceDeletionBridge:
    """Persistent Skill 27 bridge; only independent receipts can complete deletion."""

    SKILL = "elmos-data-retention-and-governance"

    def __init__(self, store: IntakeStore) -> None:
        self._store = store

    @staticmethod
    def _envelope(state: str, code: str, outputs: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "state": state,
            "code": code,
            "outputs": dict(outputs),
            "metrics": {},
            "retryable": False,
        }

    @staticmethod
    def _request(ctx: RuntimeContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "request_id": ctx.request_id,
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "actor_id": ctx.actor_id,
            "inputs": dict(payload),
            "idempotency_key": ctx.idempotency_key,
            "trace_id": ctx.trace_id,
            "policy": ctx.policy,
            "capabilities": ctx.capabilities,
        }

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name != self.SKILL:
            raise ValidationError("GOVERNANCE_BRIDGE_SKILL_INVALID")
        operation = payload.get("operation")
        if operation == "delete_status":
            expected = {"operation", "job_id", "idempotency_key", "trace_id"}
            if set(payload) != expected or payload.get("trace_id") != ctx.trace_id:
                raise ValidationError("GOVERNANCE_DELETION_STATUS_FIELDS_INVALID")
            result = self._store.governance_deletion_status(
                TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id),
                job_id=str(payload.get("job_id", "")),
            )
            completed = result["state"] == "COMPLETED"
            return self._envelope(
                "SUCCEEDED" if completed else "BLOCKED",
                "DELETION_PROPAGATION_VERIFIED" if completed else "DELETION_PROPAGATION_NOT_RUN",
                result,
            )
        if operation != "delete":
            domain_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"operation", "idempotency_key", "trace_id"}
            }
            domain_payload["action"] = str(operation).replace("_", "-")
            result = apply_retention_governance(self._request(ctx, domain_payload))
            return self._envelope(result["state"], result["code"], result["outputs"])
        expected = {"operation", "idempotency_key", "trace_id"}
        if set(payload) != expected:
            raise ValidationError("GOVERNANCE_DELETION_INPUT_FIELDS_INVALID")
        if ctx.idempotency_key is None:
            raise ValidationError("GOVERNANCE_DELETION_IDEMPOTENCY_KEY_REQUIRED")
        safe_key = require_idempotency_key(ctx.idempotency_key)
        if payload.get("idempotency_key") != safe_key or payload.get("trace_id") != ctx.trace_id:
            raise ValidationError("GOVERNANCE_DELETION_ENVELOPE_BINDING_INVALID")
        policy = _runtime_namespace(self._request(ctx, payload), "policy", "retention")
        inventory = _runtime_namespace(self._request(ctx, payload), "capabilities", "governance_inventory")
        if policy is None or not _scope_matches(policy, self._request(ctx, payload)):
            return self._envelope("BLOCKED", "RETENTION_POLICY_UNAVAILABLE", {"decision": "NOT_RUN"})
        policy_version = str(policy.get("version", ""))
        allowed = _string_set(policy.get("allowed_actions", []), "policy.retention.allowed_actions")
        if not policy_version or "delete" not in allowed:
            return self._envelope(
                "BLOCKED", "RETENTION_ACTION_NOT_AUTHORIZED",
                {"decision": "NOT_RUN", "policy_version": policy_version},
            )
        if inventory is None or inventory.get("complete") is not True:
            return self._envelope(
                "BLOCKED", "GOVERNANCE_INVENTORY_UNAVAILABLE",
                {"decision": "NOT_RUN", "policy_version": policy_version},
            )
        inventory_version = str(inventory.get("version", ""))
        objects = _sequence(inventory.get("objects", []), "capabilities.governance_inventory.objects")
        inventory_body = {
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "version": inventory_version,
            "complete": True,
            "objects": objects,
        }
        inventory_digest = inventory.get("inventory_digest")
        if (
            not inventory_version
            or not objects
            or inventory_digest != _digest(inventory_body)
        ):
            return self._envelope(
                "BLOCKED", "GOVERNANCE_INVENTORY_INTEGRITY_FAILED",
                {"decision": "NOT_RUN", "policy_version": policy_version},
            )
        result = self._store.prepare_governance_deletion(
            TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id),
            objects=objects,
            policy_version=policy_version,
            inventory_version=inventory_version,
            inventory_digest=str(inventory_digest),
            idempotency_key=safe_key,
        )
        held = result["legal_hold_count"] > 0
        return self._envelope(
            "BLOCKED",
            "RETENTION_HOLD_BLOCKS_DELETION" if held else "DELETION_PROPAGATION_NOT_RUN",
            result,
        )
