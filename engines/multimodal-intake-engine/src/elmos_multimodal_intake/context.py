"""Fail-closed model capability, context budgeting, and recovery logic."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any


class ContextContractError(ValueError):
    """Raised when context state cannot be safely interpreted."""


_MAX_CONTEXT_ITEMS = 10_000
_MAX_CONTEXT_JSON_BYTES = 8 * 1024 * 1024
_MAX_TEXT_BYTES = 4 * 1024 * 1024
_MAX_TOKEN_COUNT = 2_147_483_647
_MAX_IMAGE_DIMENSION = 100_000
_MAX_IMAGE_PIXELS = 1_000_000_000
_MAX_AUDIO_SECONDS = 24 * 60 * 60
_MAX_BINARY_BYTES = 256 * 1024 * 1024
_TRUSTED_CAPABILITY_STATES = frozenset({"TRUSTED_PROVIDER", "VERIFIED_ADMIN", "SIGNED_REGISTRY"})
_MEASUREMENT_BINDING_FIELDS = frozenset(
    {
        "item_id",
        "source_digest",
        "content_digest",
        "model_id",
        "model_version",
        "tokenizer_id",
        "tokenizer_version",
        "measured_tokens",
        "registry_version",
    }
)
_MEASUREMENT_RECORD_FIELDS = _MEASUREMENT_BINDING_FIELDS | {"measurement_digest"}
_PRESSURE_DEFAULTS: dict[str, float] = {
    "elevated": 0.65,
    "high": 0.80,
    "critical": 0.92,
    "hysteresis": 0.05,
}


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContextContractError("value must be finite JSON data") from exc


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_sha256_digest(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ContextContractError(f"{field} must be a lowercase sha256 digest")
    return value


def _strict_text(value: Any, field: str, *, maximum_bytes: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContextContractError(f"{field} must be an exact non-blank string")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise ContextContractError(f"{field} exceeds the bounded text limit")
    return value


def _inputs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    value = request.get("inputs")
    if not isinstance(value, Mapping):
        raise ContextContractError("inputs must be an object")
    return value


def _sequence(value: Any, field: str, *, maximum: int = _MAX_CONTEXT_ITEMS) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ContextContractError(f"{field} must be an array")
    if len(value) > maximum:
        raise ContextContractError(f"{field} exceeds the bounded item limit")
    return list(value)


def _bounded_int(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_TOKEN_COUNT,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContextContractError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise ContextContractError(f"{field} is outside the supported bounds")
    return value


def _positive_int(value: Any, field: str, *, maximum: int = _MAX_TOKEN_COUNT) -> int:
    return _bounded_int(value, field, minimum=1, maximum=maximum)


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContextContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ContextContractError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise ContextContractError(f"{field} is below the supported bound")
    if maximum is not None and number > maximum:
        raise ContextContractError(f"{field} exceeds the supported bound")
    return number


def _bounded_json(value: Any, field: str, *, maximum_bytes: int = _MAX_CONTEXT_JSON_BYTES) -> None:
    encoded = _canonical(value).encode("utf-8")
    if len(encoded) > maximum_bytes:
        raise ContextContractError(f"{field} exceeds the bounded JSON size")


def _verified_measurement_index(
    request: Mapping[str, Any], capabilities: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Validate trusted token measurements as exact content/model/tokenizer tuples."""

    registry = capabilities.get("verified_token_measurements")
    if registry is None or registry == {}:
        return {}
    if not isinstance(registry, Mapping):
        raise ContextContractError("verified_token_measurements must be an object")
    if set(registry) != {"version", "tenant_id", "project_id", "measurements"}:
        raise ContextContractError("verified_token_measurements has an invalid envelope")
    registry_version = _strict_text(
        registry.get("version"), "verified_token_measurements.version"
    )
    if (
        registry.get("tenant_id") != request.get("tenant_id")
        or registry.get("project_id") != request.get("project_id")
    ):
        raise ContextContractError("verified_token_measurements scope does not match the request")
    measurements = _sequence(
        registry.get("measurements"),
        "verified_token_measurements.measurements",
        maximum=_MAX_CONTEXT_ITEMS,
    )
    index: dict[str, dict[str, Any]] = {}
    for position, raw in enumerate(measurements):
        if not isinstance(raw, Mapping) or set(raw) != _MEASUREMENT_RECORD_FIELDS:
            raise ContextContractError(
                f"verified_token_measurements.measurements[{position}] has an invalid shape"
            )
        binding: dict[str, Any] = {
            "item_id": _strict_text(raw.get("item_id"), f"measurements[{position}].item_id"),
            "source_digest": _require_sha256_digest(
                raw.get("source_digest"), f"measurements[{position}].source_digest"
            ),
            "content_digest": _require_sha256_digest(
                raw.get("content_digest"), f"measurements[{position}].content_digest"
            ),
            "model_id": _strict_text(raw.get("model_id"), f"measurements[{position}].model_id"),
            "model_version": _strict_text(
                raw.get("model_version"), f"measurements[{position}].model_version"
            ),
            "tokenizer_id": _strict_text(
                raw.get("tokenizer_id"), f"measurements[{position}].tokenizer_id"
            ),
            "tokenizer_version": _strict_text(
                raw.get("tokenizer_version"), f"measurements[{position}].tokenizer_version"
            ),
            "measured_tokens": _positive_int(
                raw.get("measured_tokens"), f"measurements[{position}].measured_tokens"
            ),
            "registry_version": _strict_text(
                raw.get("registry_version"), f"measurements[{position}].registry_version"
            ),
        }
        item_id = binding["item_id"]
        if (
            binding["registry_version"] != registry_version
            or raw.get("measurement_digest") != _digest(binding)
            or item_id in index
        ):
            raise ContextContractError("verified token measurement binding is invalid")
        index[item_id] = {**binding, "measurement_digest": raw["measurement_digest"]}
    return index


def _trusted_mapping(request: Mapping[str, Any], root: str, field: str) -> Mapping[str, Any] | None:
    container = request.get(root, {})
    if not isinstance(container, Mapping):
        raise ContextContractError(f"trusted {root} must be an object")
    value = container.get(field)
    return value if isinstance(value, Mapping) else None


def _trusted_capability_snapshot(
    request: Mapping[str, Any],
    supplied: Any,
) -> Mapping[str, Any] | None:
    if not isinstance(supplied, Mapping):
        return None
    trusted = _trusted_mapping(request, "capabilities", "model_capability_snapshot")
    if trusted is None or dict(trusted) != dict(supplied):
        return None
    claimed = supplied.get("snapshot_digest")
    body = dict(supplied)
    body.pop("snapshot_digest", None)
    if not isinstance(claimed, str) or claimed != _digest(body):
        return None
    if str(supplied.get("trust", "UNKNOWN")).upper() not in _TRUSTED_CAPABILITY_STATES:
        return None
    try:
        observed_at = _timestamp(supplied.get("observed_at"))
        expires_at = _timestamp(supplied.get("expires_at"))
        capability_registry = request.get("capabilities", {})
        if not isinstance(capability_registry, Mapping):
            return None
        configured_now = _finite_number(
            capability_registry.get("model_capability_now", time.time()),
            "model_capability_now",
            minimum=0,
        )
        now = max(time.time(), configured_now)
    except (ContextContractError, TypeError, ValueError):
        return None
    if observed_at > now + 300 or expires_at <= observed_at or expires_at <= now:
        return None
    return supplied


def _timestamp(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite_number(value, "capability timestamp", minimum=0)
    if isinstance(value, str):
        candidate = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        timestamp = parsed.timestamp()
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ContextContractError("capability timestamp is invalid")
        return timestamp
    raise ContextContractError("capability timestamp is invalid")


def discover_model_capabilities(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and version a provider/model capability observation."""

    values = _inputs(request)
    observation = values.get("observation")
    if not isinstance(observation, Mapping):
        raise ContextContractError("inputs.observation must be an object")
    _bounded_json(observation, "inputs.observation", maximum_bytes=64 * 1024)
    if "now" in values:
        return {
            "state": "BLOCKED",
            "code": "MODEL_CAPABILITY_CLOCK_UNTRUSTED",
            "outputs": {"usable": False},
        }
    trusted_observation = _trusted_mapping(request, "capabilities", "model_capability_observation")
    if trusted_observation is None or dict(trusted_observation) != dict(observation):
        return {
            "state": "BLOCKED",
            "code": "MODEL_CAPABILITY_UNTRUSTED",
            "outputs": {"trust": "UNVERIFIED", "usable": False},
        }
    trust = str(trusted_observation.get("trust", "UNKNOWN")).upper()
    if trust not in _TRUSTED_CAPABILITY_STATES:
        return {
            "state": "BLOCKED",
            "code": "MODEL_CAPABILITY_UNTRUSTED",
            "outputs": {"trust": trust, "usable": False},
        }
    observed_at = _timestamp(observation.get("observed_at"))
    expires_at = _timestamp(observation.get("expires_at"))
    trusted_clock = request.get("capabilities", {}).get("model_capability_now", time.time())
    configured_now = _finite_number(trusted_clock, "model_capability_now", minimum=0)
    now = max(time.time(), configured_now)
    if observed_at > now + 300 or expires_at <= observed_at or expires_at <= now:
        return {
            "state": "BLOCKED",
            "code": "MODEL_CAPABILITY_STALE",
            "outputs": {"observed_at": observed_at, "expires_at": expires_at, "usable": False},
        }
    modalities = _sequence(observation.get("modalities", ["text"]), "observation.modalities", maximum=32)
    normalized_modalities = sorted({str(item).strip().lower() for item in modalities if str(item).strip()})
    if not normalized_modalities:
        raise ContextContractError("at least one model modality is required")
    snapshot: dict[str, Any] = {
        "provider": str(observation.get("provider", "")),
        "model_id": str(observation.get("model_id", "")),
        "model_version": str(observation.get("model_version", "")),
        "context_window_tokens": _positive_int(observation.get("context_window_tokens"), "context_window_tokens"),
        "max_output_tokens": _positive_int(observation.get("max_output_tokens"), "max_output_tokens"),
        "modalities": normalized_modalities,
        "source": str(observation.get("source", "")),
        "trust": trust,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "version": _positive_int(observation.get("version", 1), "capability version", maximum=1_000_000),
    }
    if not snapshot["provider"] or not snapshot["model_id"] or not snapshot["source"]:
        raise ContextContractError("provider, model_id, and source are required")
    if any(len(str(snapshot[field]).encode("utf-8")) > 512 for field in ("provider", "model_id", "model_version", "source")):
        raise ContextContractError("model capability identity fields exceed the bounded length")
    if snapshot["max_output_tokens"] > snapshot["context_window_tokens"]:
        raise ContextContractError("max_output_tokens cannot exceed context_window_tokens")
    snapshot["snapshot_id"] = "mcs_" + _digest(snapshot)[7:31]
    snapshot["snapshot_digest"] = _digest(snapshot)
    previous = values.get("previous_snapshot")
    changes: list[dict[str, Any]] = []
    if isinstance(previous, Mapping):
        _bounded_json(previous, "previous_snapshot", maximum_bytes=64 * 1024)
        for field in ("context_window_tokens", "max_output_tokens", "model_version", "modalities"):
            if previous.get(field) != snapshot.get(field):
                changes.append({"field": field, "before": previous.get(field), "after": snapshot.get(field)})
    return {
        "state": "SUCCEEDED",
        "code": "MODEL_CAPABILITY_SNAPSHOT_CREATED",
        "outputs": {"snapshot": snapshot, "changes": changes, "requires_rebudget": bool(changes)},
    }


def check_codex_capacity_parity(request: Mapping[str, Any]) -> dict[str, Any]:
    """Compare a trusted capability snapshot with a versioned parity policy."""

    values = _inputs(request)
    if "parity_policy" in values or "policy" in values:
        return {
            "state": "BLOCKED",
            "code": "PARITY_POLICY_UNTRUSTED",
            "outputs": {"compatible": False},
        }
    snapshot = _trusted_capability_snapshot(request, values.get("capability_snapshot"))
    policy = _trusted_mapping(request, "policy", "context_parity")
    if snapshot is None:
        return {"state": "BLOCKED", "code": "CAPABILITY_UNKNOWN", "outputs": {"compatible": False}}
    if policy is None:
        return {"state": "BLOCKED", "code": "PARITY_POLICY_MISSING", "outputs": {"compatible": False}}
    if set(policy) - {"minimum_context_window_tokens", "minimum_output_tokens", "version"}:
        raise ContextContractError("policy.context_parity contains unsupported fields")
    window = _positive_int(snapshot.get("context_window_tokens"), "context_window_tokens")
    output = _positive_int(snapshot.get("max_output_tokens"), "max_output_tokens")
    required_window = _positive_int(policy.get("minimum_context_window_tokens"), "minimum_context_window_tokens")
    required_output = _positive_int(policy.get("minimum_output_tokens"), "minimum_output_tokens")
    compatible = window >= required_window and output >= required_output
    strategy = "DIRECT" if compatible else "RETRIEVE_PARTITION_COMPACT"
    return {
        "state": "SUCCEEDED" if compatible else "PARTIAL",
        "code": "CODEX_PARITY_COMPATIBLE" if compatible else "CODEX_PARITY_REQUIRES_ADAPTATION",
        "outputs": {
            "compatible": compatible,
            "strategy": strategy,
            "observed": {"context_window_tokens": window, "max_output_tokens": output},
            "required": {"context_window_tokens": required_window, "max_output_tokens": required_output},
            "policy_version": str(policy.get("version", "unknown")),
        },
    }


def account_multimodal_tokens(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic measured or conservative token estimates per source."""

    values = _inputs(request)
    items = _sequence(values.get("items", []), "inputs.items", maximum=_MAX_CONTEXT_ITEMS)
    if not items:
        return {
            "state": "BLOCKED",
            "code": "TOKEN_INPUT_EMPTY",
            "outputs": {"estimates": [], "safe_total_tokens": 0, "unbounded_item_ids": []},
        }
    model_version = str(values.get("model_version", "unknown"))
    estimator_version = str(values.get("estimator_version", "multimodal-upper-bound-v1"))
    capabilities = request.get("capabilities", {})
    if not isinstance(capabilities, Mapping):
        raise ContextContractError("trusted capabilities must be an object")
    verified_measurements = _verified_measurement_index(request, capabilities)
    estimates: list[dict[str, Any]] = []
    blocked: list[str] = []
    seen_ids: set[str] = set()
    total_source_bytes = 0
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ContextContractError(f"inputs.items[{index}] must be an object")
        item_id = _strict_text(
            item.get("item_id", f"item_{index + 1}"),
            f"inputs.items[{index}].item_id",
        )
        if item_id in seen_ids:
            raise ContextContractError("token accounting item_id must be unique")
        seen_ids.add(item_id)
        modality = str(item.get("modality", "text")).lower()
        measured = item.get("measured_tokens")
        status = "MEASURED" if measured is not None else "ESTIMATED_UPPER_BOUND"
        measurement_binding_digest: str | None = None
        if measured is not None:
            tokens = _positive_int(measured, "measured_tokens")
            source_digest = _require_sha256_digest(
                item.get("source_digest"), f"inputs.items[{index}].source_digest"
            )
            model_id = _strict_text(values.get("model_id"), "inputs.model_id")
            measured_model_version = _strict_text(
                values.get("model_version"), "inputs.model_version"
            )
            tokenizer_id = _strict_text(values.get("tokenizer_id"), "inputs.tokenizer_id")
            tokenizer_version = _strict_text(
                values.get("tokenizer_version"), "inputs.tokenizer_version"
            )
            if any(not isinstance(key, str) for key in item):
                raise ContextContractError("measured token item keys must be strings")
            content_body = {
                key: value for key, value in item.items() if key != "measured_tokens"
            }
            content_digest = _digest(content_body)
            trusted_measurement = verified_measurements.get(item_id)
            if trusted_measurement is None:
                blocked.append(item_id)
                continue
            expected_binding = {
                "item_id": item_id,
                "source_digest": source_digest,
                "content_digest": content_digest,
                "model_id": model_id,
                "model_version": measured_model_version,
                "tokenizer_id": tokenizer_id,
                "tokenizer_version": tokenizer_version,
                "measured_tokens": tokens,
                "registry_version": trusted_measurement["registry_version"],
            }
            if any(
                trusted_measurement.get(field) != value
                for field, value in expected_binding.items()
            ):
                blocked.append(item_id)
                continue
            lower = upper = tokens
            model_version = measured_model_version
            status = "MEASURED_VERIFIED"
            measurement_binding_digest = trusted_measurement["measurement_digest"]
        elif modality in {"text", "code", "document", "tool_schema", "tool_result"}:
            text = item.get("text", "")
            if not isinstance(text, str):
                raise ContextContractError("token accounting text must be a string")
            raw = text.encode("utf-8")
            if not raw:
                blocked.append(item_id)
                continue
            if len(raw) > _MAX_TEXT_BYTES:
                raise ContextContractError("token accounting text exceeds the per-item byte limit")
            total_source_bytes += len(raw)
            if total_source_bytes > _MAX_CONTEXT_JSON_BYTES:
                raise ContextContractError("token accounting input exceeds the cumulative byte limit")
            tokens = max(1, math.ceil(len(raw) / 3))
            lower = max(1, math.floor(tokens * 0.55))
            upper = tokens
        elif modality in {"image", "ui", "diagram"}:
            width = _positive_int(item.get("width"), "width", maximum=_MAX_IMAGE_DIMENSION)
            height = _positive_int(item.get("height"), "height", maximum=_MAX_IMAGE_DIMENSION)
            if width * height > _MAX_IMAGE_PIXELS:
                raise ContextContractError("image pixel count exceeds the supported limit")
            tiles = math.ceil(width / 512) * math.ceil(height / 512)
            tokens = max(85, 85 + tiles * 170)
            lower = max(1, tokens // 2)
            upper = tokens
        elif modality in {"audio", "transcript"}:
            duration = _finite_number(
                item.get("duration_seconds", 0),
                "duration_seconds",
                minimum=0,
                maximum=_MAX_AUDIO_SECONDS,
            )
            if duration == 0:
                blocked.append(item_id)
                continue
            tokens = max(1, math.ceil(duration * 12))
            lower = max(1, math.ceil(duration * 4))
            upper = tokens
        else:
            byte_count = _bounded_int(
                item.get("byte_count", 0),
                "byte_count",
                minimum=0,
                maximum=_MAX_BINARY_BYTES,
            )
            if byte_count == 0:
                blocked.append(item_id)
                continue
            tokens = max(1, math.ceil(byte_count / 2))
            lower = max(1, math.ceil(byte_count / 8))
            upper = tokens
            status = "ESTIMATED_UNKNOWN_MODALITY_UPPER_BOUND"
        estimate = {
            "item_id": item_id,
            "source_digest": str(item.get("source_digest", "")),
            "modality": modality,
            "tokens": tokens,
            "lower_bound": lower,
            "upper_bound": upper,
            "status": status,
            "model_version": model_version,
            "estimator_version": estimator_version,
        }
        if measurement_binding_digest is not None:
            estimate["measurement_binding_digest"] = measurement_binding_digest
            estimate["model_id"] = model_id
            estimate["tokenizer_id"] = tokenizer_id
            estimate["tokenizer_version"] = tokenizer_version
        estimate["estimate_digest"] = _digest(estimate)
        estimates.append(estimate)
    total = sum(item["upper_bound"] for item in estimates)
    if total > _MAX_TOKEN_COUNT:
        raise ContextContractError("multimodal token total exceeds the supported limit")
    return {
        "state": "BLOCKED" if blocked else "SUCCEEDED",
        "code": "TOKEN_ESTIMATE_UNBOUNDED" if blocked else "MULTIMODAL_TOKENS_ACCOUNTED",
        "outputs": {
            "estimates": estimates,
            "safe_total_tokens": total,
            "unbounded_item_ids": blocked,
            "accounting_digest": _digest(estimates),
        },
    }


def calculate_context_budget(request: Mapping[str, Any]) -> dict[str, Any]:
    """Compute the exact pre-call budget using safe upper bounds."""

    values = _inputs(request)
    capability = _trusted_capability_snapshot(request, values.get("capability_snapshot"))
    if capability is None:
        return {"state": "BLOCKED", "code": "CAPABILITY_UNKNOWN", "outputs": {"allowed": False}}
    window = _positive_int(capability.get("context_window_tokens"), "context_window_tokens")
    max_output = _positive_int(capability.get("max_output_tokens"), "max_output_tokens")
    usage = values.get("usage")
    if not isinstance(usage, Mapping):
        raise ContextContractError("inputs.usage must be an object")
    if len(usage) > 128:
        raise ContextContractError("usage categories exceed the bounded limit")
    categories: dict[str, int] = {}
    for key, raw in usage.items():
        number = _finite_number(raw, f"usage.{key}", minimum=0, maximum=_MAX_TOKEN_COUNT)
        categories[str(key)] = int(math.ceil(number))
    reserved_output = _positive_int(
        values.get("reserved_output_tokens", max_output),
        "reserved_output_tokens",
        maximum=max_output,
    )
    headroom = _positive_int(
        values.get("safety_headroom_tokens", max(1, math.ceil(window * 0.05))),
        "safety_headroom_tokens",
        maximum=window,
    )
    input_used = sum(categories.values())
    if input_used > _MAX_TOKEN_COUNT:
        raise ContextContractError("context usage exceeds the supported token limit")
    effective_input = window - reserved_output - headroom
    remaining = effective_input - input_used
    allowed = effective_input > 0 and remaining >= 0
    snapshot = {
        "context_window_tokens": window,
        "max_output_tokens": max_output,
        "usage": dict(sorted(categories.items())),
        "input_used_tokens": input_used,
        "reserved_output_tokens": reserved_output,
        "safety_headroom_tokens": headroom,
        "effective_input_budget": effective_input,
        "remaining_tokens": remaining,
        "pressure_ratio": round(input_used / max(1, effective_input), 8),
        "allowed": allowed,
    }
    snapshot["budget_digest"] = _digest(snapshot)
    return {
        "state": "SUCCEEDED" if allowed else "BLOCKED",
        "code": "CONTEXT_BUDGET_ALLOWED" if allowed else "CONTEXT_BUDGET_EXCEEDED",
        "outputs": snapshot,
    }


def pack_context(request: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministically rank and pack candidates while pinning P0/P1."""

    values = _inputs(request)
    candidates = _sequence(values.get("candidates", []), "inputs.candidates", maximum=_MAX_CONTEXT_ITEMS)
    budget_value = values.get("effective_input_budget", 0)
    if budget_value == 0:
        return {"state": "BLOCKED", "code": "CONTEXT_BUDGET_MISSING", "outputs": {"plan": []}}
    budget = _positive_int(budget_value, "effective_input_budget")
    if not candidates:
        return {"state": "BLOCKED", "code": "CONTEXT_CANDIDATES_EMPTY", "outputs": {"plan": []}}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(candidates):
        if not isinstance(raw, Mapping):
            raise ContextContractError(f"inputs.candidates[{index}] must be an object")
        item_id = str(raw.get("item_id", f"candidate_{index + 1}"))
        if not item_id or len(item_id.encode("utf-8")) > 512 or item_id in seen:
            raise ContextContractError(f"duplicate context candidate: {item_id}")
        seen.add(item_id)
        priority = str(raw.get("priority", "P5")).upper()
        if priority not in {f"P{i}" for i in range(6)}:
            raise ContextContractError(f"invalid priority: {priority}")
        tokens = _positive_int(raw.get("tokens"), "candidate.tokens")
        relevance = _finite_number(raw.get("relevance", 0.0), "candidate.relevance", minimum=0, maximum=1)
        freshness = _finite_number(raw.get("freshness", 0.0), "candidate.freshness", minimum=0, maximum=1)
        _bounded_json(raw.get("anchor"), "candidate.anchor", maximum_bytes=64 * 1024)
        normalized.append(
            {
                "item_id": item_id,
                "priority": priority,
                "priority_rank": int(priority[1]),
                "tokens": tokens,
                "relevance": relevance,
                "freshness": freshness,
                "source_diversity_key": str(raw.get("source_diversity_key", item_id)),
                "anchor": raw.get("anchor"),
            }
        )
    pinned = [item for item in normalized if item["priority_rank"] <= 1]
    pinned_tokens = sum(item["tokens"] for item in pinned)
    if pinned_tokens > budget:
        return {
            "state": "BLOCKED",
            "code": "PINNED_CONTEXT_EXCEEDS_BUDGET",
            "outputs": {"pinned_tokens": pinned_tokens, "budget": budget, "pinned_item_ids": [item["item_id"] for item in pinned]},
        }
    ordered = sorted(
        normalized,
        key=lambda item: (
            item["priority_rank"],
            -item["relevance"],
            -item["freshness"],
            item["source_diversity_key"],
            item["item_id"],
        ),
    )
    used = 0
    included: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for item in ordered:
        if used + item["tokens"] <= budget:
            used += item["tokens"]
            included.append({**item, "decision": "INCLUDED", "reason": "PINNED" if item["priority_rank"] <= 1 else "RANKED_WITHIN_BUDGET"})
        else:
            deferred.append({**item, "decision": "DEFERRED", "reason": "INSUFFICIENT_REMAINING_BUDGET"})
    plan = {
        "budget": budget,
        "used_tokens": used,
        "remaining_tokens": budget - used,
        "included": included,
        "deferred": deferred,
    }
    plan["plan_digest"] = _digest(plan)
    return {"state": "SUCCEEDED", "code": "CONTEXT_PACKED", "outputs": plan}


def monitor_context_pressure(request: Mapping[str, Any]) -> dict[str, Any]:
    """Apply configurable thresholds and hysteresis before hard overflow."""

    values = _inputs(request)
    if "thresholds" in values or "policy" in values or "policy_version" in values:
        return {
            "state": "BLOCKED",
            "code": "CONTEXT_PRESSURE_POLICY_UNTRUSTED",
            "outputs": {"pressure_state": "UNKNOWN", "action": "BLOCK_NEW_LOADS"},
        }
    used = values.get("used_tokens")
    budget = values.get("effective_input_budget")
    try:
        used_number = _finite_number(used, "used_tokens", minimum=0, maximum=_MAX_TOKEN_COUNT)
        budget_number = _finite_number(budget, "effective_input_budget", minimum=0, maximum=_MAX_TOKEN_COUNT)
    except ContextContractError:
        return {
            "state": "BLOCKED",
            "code": "CONTEXT_USAGE_MISSING",
            "outputs": {"pressure_state": "UNKNOWN", "action": "BLOCK_NEW_LOADS"},
        }
    if budget_number == 0:
        return {
            "state": "BLOCKED",
            "code": "CONTEXT_USAGE_MISSING",
            "outputs": {"pressure_state": "UNKNOWN", "action": "BLOCK_NEW_LOADS"},
        }
    policy_root = request.get("policy", {})
    if not isinstance(policy_root, Mapping):
        raise ContextContractError("trusted policy must be an object")
    raw_policy = policy_root.get("context_pressure")
    if raw_policy is None:
        thresholds: Mapping[str, Any] = _PRESSURE_DEFAULTS
    elif isinstance(raw_policy, Mapping):
        thresholds = raw_policy
    else:
        raise ContextContractError("policy.context_pressure must be an object")
    if set(thresholds) - {"elevated", "high", "critical", "hysteresis", "version"}:
        raise ContextContractError("policy.context_pressure contains unsupported fields")
    elevated = _finite_number(thresholds.get("elevated", _PRESSURE_DEFAULTS["elevated"]), "elevated", minimum=0, maximum=1)
    high = _finite_number(thresholds.get("high", _PRESSURE_DEFAULTS["high"]), "high", minimum=0, maximum=1)
    critical = _finite_number(thresholds.get("critical", _PRESSURE_DEFAULTS["critical"]), "critical", minimum=0, maximum=1)
    hysteresis = _finite_number(thresholds.get("hysteresis", _PRESSURE_DEFAULTS["hysteresis"]), "hysteresis", minimum=0, maximum=1)
    if not (0 < elevated < high < critical < 1 and 0 <= hysteresis < elevated):
        raise ContextContractError("pressure thresholds must be ordered below the hard limit")
    ratio = used_number / budget_number
    previous = str(values.get("previous_state", "NORMAL")).upper()
    levels = ["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]
    if previous not in levels:
        raise ContextContractError("previous pressure state is invalid")
    target = "CRITICAL" if ratio >= critical else "HIGH" if ratio >= high else "ELEVATED" if ratio >= elevated else "NORMAL"
    if previous in levels and levels.index(target) < levels.index(previous):
        release_threshold = {"CRITICAL": critical, "HIGH": high, "ELEVATED": elevated}.get(previous, 0) - hysteresis
        if ratio >= release_threshold:
            target = previous
    action = {"NORMAL": "NONE", "ELEVATED": "PREFETCH_COMPACTION", "HIGH": "COMPACT_AND_DEFER", "CRITICAL": "BLOCK_AND_CHECKPOINT"}[target]
    snapshot = {
        "pressure_state": target,
        "previous_state": previous,
        "ratio": round(ratio, 8),
        "action": action,
        "policy_version": str(thresholds.get("version", "built-in-1")),
    }
    snapshot["snapshot_digest"] = _digest(snapshot)
    return {"state": "SUCCEEDED", "code": f"CONTEXT_PRESSURE_{target}", "outputs": snapshot}


def compact_context(request: Mapping[str, Any]) -> dict[str, Any]:
    """Produce a structured checkpoint; never replace state with free text."""

    values = _inputs(request)
    state = values.get("state")
    if not isinstance(state, Mapping):
        raise ContextContractError("inputs.state must be an object")
    _bounded_json(state, "inputs.state")
    required = ("goal", "latest_user_request", "constraints", "acceptance_criteria", "todos")
    missing = [field for field in required if field not in state or state[field] in (None, "", [])]
    if missing:
        return {
            "state": "BLOCKED",
            "code": "CRITICAL_CONTEXT_FIELDS_MISSING",
            "outputs": {"missing_fields": missing, "original_unchanged": True},
        }
    facts = _sequence(state.get("facts", []), "state.facts", maximum=_MAX_CONTEXT_ITEMS)
    compacted_facts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, fact in enumerate(facts):
        if not isinstance(fact, Mapping):
            raise ContextContractError(f"state.facts[{index}] must be an object")
        anchor = fact.get("anchor")
        if bool(fact.get("critical")) and not isinstance(anchor, Mapping):
            return {
                "state": "BLOCKED",
                "code": "CRITICAL_FACT_WITHOUT_ANCHOR",
                "outputs": {"fact_index": index, "original_unchanged": True},
            }
        identity = _digest({"type": fact.get("type"), "value": fact.get("value"), "anchor": anchor})
        if identity not in seen:
            seen.add(identity)
            compacted_facts.append(dict(fact))
    modified_files = _sequence(state.get("modified_files", []), "modified_files", maximum=_MAX_CONTEXT_ITEMS)
    test_state = _sequence(state.get("test_state", []), "test_state", maximum=_MAX_CONTEXT_ITEMS)
    calculated_history_digest = _digest(state)
    claimed_history_digest = values.get("source_history_digest")
    if claimed_history_digest is not None and claimed_history_digest != calculated_history_digest:
        return {
            "state": "BLOCKED",
            "code": "SOURCE_HISTORY_DIGEST_MISMATCH",
            "outputs": {"original_unchanged": True},
        }
    checkpoint = {
        "schema_version": "1.0.0",
        **{field: state[field] for field in required},
        "facts": compacted_facts,
        "modified_files": modified_files,
        "test_state": test_state,
        "source_history_digest": calculated_history_digest,
    }
    _bounded_json(checkpoint, "compacted checkpoint")
    checkpoint["checkpoint_digest"] = _digest(checkpoint)
    return {
        "state": "SUCCEEDED",
        "code": "STRUCTURED_CONTEXT_COMPACTED",
        "outputs": {"checkpoint": checkpoint, "original_unchanged": True, "critical_field_retention": 1.0},
    }


def _checkpoint_identity(request: Mapping[str, Any]) -> tuple[str, str, str]:
    tenant_id = str(request.get("tenant_id", ""))
    project_id = str(request.get("project_id", ""))
    request_id = str(request.get("request_id", ""))
    if not tenant_id or not project_id or not request_id:
        raise ContextContractError("checkpoint tenant_id, project_id, and request_id are required")
    return tenant_id, project_id, request_id


def _verified_effect_receipt_ids(
    request: Mapping[str, Any],
    *,
    payload_digest: str,
    source_request_id: str,
) -> set[str]:
    capabilities = request.get("capabilities", {})
    if not isinstance(capabilities, Mapping):
        raise ContextContractError("trusted capabilities must be an object")
    raw_receipts = capabilities.get("verified_effect_receipts", [])
    receipts = _sequence(raw_receipts, "capabilities.verified_effect_receipts", maximum=1_000)
    tenant_id, project_id, _ = _checkpoint_identity(request)
    verified: set[str] = set()
    for index, raw in enumerate(receipts):
        if not isinstance(raw, Mapping):
            raise ContextContractError(f"verified_effect_receipts[{index}] must be an object")
        receipt_id = str(raw.get("receipt_id", ""))
        if (
            not receipt_id
            or raw.get("verified") is not True
            or str(raw.get("tenant_id", "")) != tenant_id
            or str(raw.get("project_id", "")) != project_id
            or str(raw.get("request_id", "")) != source_request_id
            or str(raw.get("payload_digest", "")) != payload_digest
        ):
            raise ContextContractError("verified effect receipt is not bound to this checkpoint scope")
        verified.add(receipt_id)
    return verified


def checkpoint_and_recover(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create or restore a digest-, scope-, request-, and payload-bound checkpoint."""

    values = _inputs(request)
    authority_fields = {
        "effect_receipts",
        "existing_effect_receipts",
        "receipts",
        "consent",
        "authorization",
        "restore_binding",
    }
    if authority_fields & set(values):
        return {
            "state": "BLOCKED",
            "code": "CHECKPOINT_AUTHORITY_INPUT_UNTRUSTED",
            "outputs": {"restored": False},
        }
    tenant_id, project_id, request_id = _checkpoint_identity(request)
    action = str(values.get("action", "create")).lower()
    if action == "create":
        payload = values.get("payload")
        if not isinstance(payload, Mapping):
            raise ContextContractError("checkpoint payload must be an object")
        _bounded_json(payload, "checkpoint payload")
        payload_body = dict(payload)
        payload_digest = _digest(payload_body)
        receipt_ids = _verified_effect_receipt_ids(
            request,
            payload_digest=payload_digest,
            source_request_id=request_id,
        )
        created_checkpoint: dict[str, Any] = {
            "schema_version": "1.0.0",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "request_id": request_id,
            "task_id": str(values.get("task_id", "")),
            "package_version": str(values.get("package_version", "")),
            "model_capability_snapshot_id": str(values.get("model_capability_snapshot_id", "")),
            "payload": payload_body,
            "payload_digest": payload_digest,
            "effect_receipt_ids": sorted(receipt_ids),
        }
        if not created_checkpoint["task_id"] or not created_checkpoint["package_version"]:
            raise ContextContractError("task_id and package_version are required")
        _bounded_json(created_checkpoint, "checkpoint")
        created_checkpoint["checkpoint_digest"] = _digest(created_checkpoint)
        return {
            "state": "SUCCEEDED",
            "code": "CONTEXT_CHECKPOINT_CREATED",
            "outputs": {"checkpoint": created_checkpoint},
        }
    if action != "restore":
        raise ContextContractError("checkpoint action must be create or restore")
    restored_checkpoint = values.get("checkpoint")
    if not isinstance(restored_checkpoint, Mapping):
        raise ContextContractError("checkpoint must be an object")
    _bounded_json(restored_checkpoint, "checkpoint")
    claimed = restored_checkpoint.get("checkpoint_digest")
    body = dict(restored_checkpoint)
    body.pop("checkpoint_digest", None)
    expected_fields = {
        "schema_version",
        "tenant_id",
        "project_id",
        "request_id",
        "task_id",
        "package_version",
        "model_capability_snapshot_id",
        "payload",
        "payload_digest",
        "effect_receipt_ids",
        "checkpoint_digest",
    }
    if (
        set(restored_checkpoint) != expected_fields
        or claimed != _digest(body)
        or restored_checkpoint.get("schema_version") != "1.0.0"
    ):
        return {"state": "BLOCKED", "code": "CHECKPOINT_CORRUPT", "outputs": {"restored": False}}
    if (
        str(restored_checkpoint.get("tenant_id", "")) != tenant_id
        or str(restored_checkpoint.get("project_id", "")) != project_id
    ):
        return {"state": "BLOCKED", "code": "CHECKPOINT_SCOPE_DENIED", "outputs": {"restored": False}}
    payload = restored_checkpoint.get("payload")
    if (
        not isinstance(payload, Mapping)
        or restored_checkpoint.get("payload_digest") != _digest(payload)
    ):
        return {"state": "BLOCKED", "code": "CHECKPOINT_PAYLOAD_MISMATCH", "outputs": {"restored": False}}
    source_request_id = str(restored_checkpoint.get("request_id", ""))
    if not source_request_id:
        return {"state": "BLOCKED", "code": "CHECKPOINT_REQUEST_BINDING_MISSING", "outputs": {"restored": False}}
    binding = _trusted_mapping(request, "capabilities", "checkpoint_restore_binding")
    required_binding = {
        "authorized": True,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "source_request_id": source_request_id,
        "restore_request_id": request_id,
        "payload_digest": str(restored_checkpoint.get("payload_digest", "")),
        "checkpoint_digest": str(claimed),
    }
    if binding is None or any(binding.get(key) != value for key, value in required_binding.items()):
        return {
            "state": "BLOCKED",
            "code": "CHECKPOINT_RESTORE_AUTHORIZATION_REQUIRED",
            "outputs": {"restored": False},
        }
    current_package_version = str(values.get("current_package_version", ""))
    if (
        not current_package_version
        or str(restored_checkpoint.get("package_version")) != current_package_version
    ):
        return {"state": "BLOCKED", "code": "CHECKPOINT_VERSION_INCOMPATIBLE", "outputs": {"restored": False}}
    trusted_receipts = _verified_effect_receipt_ids(
        request,
        payload_digest=str(restored_checkpoint.get("payload_digest")),
        source_request_id=source_request_id,
    )
    checkpoint_receipts = {
        str(item)
        for item in _sequence(
            restored_checkpoint.get("effect_receipt_ids", []),
            "checkpoint.effect_receipt_ids",
            maximum=1_000,
        )
    }
    effects_to_skip = sorted(trusted_receipts & checkpoint_receipts)
    effects_requiring_reconciliation = sorted(checkpoint_receipts - trusted_receipts)
    return {
        "state": "PARTIAL" if effects_requiring_reconciliation else "SUCCEEDED",
        "code": "CONTEXT_CHECKPOINT_EFFECT_RECONCILIATION_REQUIRED" if effects_requiring_reconciliation else "CONTEXT_CHECKPOINT_RESTORED",
        "outputs": {
            "restored": True,
            "payload": dict(payload),
            "payload_digest": restored_checkpoint.get("payload_digest"),
            "source_request_id": source_request_id,
            "restore_request_id": request_id,
            "effects_to_skip": effects_to_skip,
            "effects_requiring_reconciliation": effects_requiring_reconciliation,
        },
    }


def rehydrate_context(request: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve exact source references from a trusted, scope-bound catalog."""

    values = _inputs(request)
    if {
        "sources",
        "tenant_id",
        "project_id",
        "authorized_source_ids",
        "authorized_tools",
        "permission",
        "permissions",
        "policy",
        "consent",
        "authorization",
        "override",
        "receipt",
        "receipts",
    } & set(values):
        return {"state": "BLOCKED", "code": "REHYDRATION_CATALOG_INPUT_UNTRUSTED", "outputs": {"loaded": []}}
    requested_values = _sequence(values.get("source_ids", []), "inputs.source_ids", maximum=_MAX_CONTEXT_ITEMS)
    requested_ids: list[str] = []
    seen_requested: set[str] = set()
    for index, raw_id in enumerate(requested_values):
        if not isinstance(raw_id, str):
            raise ContextContractError(f"inputs.source_ids[{index}] must be a string")
        source_id = raw_id
        if not source_id or len(source_id.encode("utf-8")) > 256 or source_id in seen_requested:
            raise ContextContractError(f"inputs.source_ids[{index}] must be bounded and unique")
        seen_requested.add(source_id)
        requested_ids.append(source_id)
    if not requested_ids:
        return {"state": "BLOCKED", "code": "REHYDRATION_SOURCE_IDS_EMPTY", "outputs": {"loaded": []}}
    tenant_id_value = request.get("tenant_id")
    project_id_value = request.get("project_id")
    if not isinstance(tenant_id_value, str) or not tenant_id_value or not isinstance(project_id_value, str) or not project_id_value:
        return {"state": "BLOCKED", "code": "REHYDRATION_CATALOG_UNAVAILABLE", "outputs": {"loaded": []}}
    tenant_id = tenant_id_value
    project_id = project_id_value
    package_version_value = values.get("package_version")
    if (
        not isinstance(package_version_value, str)
        or not package_version_value
        or len(package_version_value.encode("utf-8")) > 256
    ):
        raise ContextContractError("package_version must be a bounded non-empty string")
    package_version = package_version_value
    trusted = _trusted_mapping(request, "capabilities", "rehydration_catalog")
    if (
        trusted is None
        or trusted.get("verified") is not True
        or str(trusted.get("tenant_id", "")) != tenant_id
        or str(trusted.get("project_id", "")) != project_id
        or str(trusted.get("package_version", "")) != package_version
    ):
        return {"state": "BLOCKED", "code": "REHYDRATION_CATALOG_UNAVAILABLE", "outputs": {"loaded": []}}
    raw_sources = _sequence(trusted.get("sources", []), "capabilities.rehydration_catalog.sources", maximum=_MAX_CONTEXT_ITEMS)
    _bounded_json(raw_sources, "capabilities.rehydration_catalog.sources")
    trusted_max_tokens = _positive_int(trusted.get("max_tokens"), "rehydration_catalog.max_tokens")
    catalog_binding = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "package_version": package_version,
        "sources": raw_sources,
        "max_tokens": trusted_max_tokens,
    }
    if trusted.get("catalog_digest") != _digest(catalog_binding):
        return {"state": "BLOCKED", "code": "REHYDRATION_CATALOG_DIGEST_MISMATCH", "outputs": {"loaded": []}}
    by_id: dict[str, dict[str, Any]] = {}
    cumulative_bytes = 0
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, Mapping):
            raise ContextContractError(f"rehydration catalog source {index} must be an object")
        source_id_value = raw.get("source_id")
        if (
            not isinstance(source_id_value, str)
            or not source_id_value
            or len(source_id_value.encode("utf-8")) > 256
            or source_id_value in by_id
        ):
            raise ContextContractError("rehydration catalog source IDs must be non-empty and unique")
        source_id = source_id_value
        if "tenant_id" in raw and str(raw.get("tenant_id")) != tenant_id:
            raise ContextContractError("rehydration source contradicts the trusted tenant scope")
        if "project_id" in raw and str(raw.get("project_id")) != project_id:
            raise ContextContractError("rehydration source contradicts the trusted project scope")
        if "package_version" in raw and str(raw.get("package_version")) != package_version:
            raise ContextContractError("rehydration source contradicts the trusted package version")
        content = raw.get("content")
        if not isinstance(content, str):
            raise ContextContractError("rehydration source content must be text")
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_TEXT_BYTES or len(encoded) > _MAX_CONTEXT_JSON_BYTES - cumulative_bytes:
            raise ContextContractError("rehydration source content exceeds the bounded byte limit")
        cumulative_bytes += len(encoded)
        claimed_digest = _require_sha256_digest(raw.get("content_digest"), "rehydration source content_digest")
        if claimed_digest != _digest(encoded):
            return {
                "state": "BLOCKED",
                "code": "REHYDRATION_HASH_MISMATCH",
                "outputs": {"loaded": [], "source_id": source_id},
            }
        anchor = raw.get("anchor")
        if not isinstance(anchor, Mapping) or not anchor:
            raise ContextContractError("rehydration source requires a provenance anchor")
        _bounded_json(anchor, "rehydration source anchor", maximum_bytes=64 * 1024)
        by_id[source_id] = {
            "source_id": source_id,
            "content": content,
            "content_digest": claimed_digest,
            "tokens": _positive_int(raw.get("tokens"), "source.tokens"),
            "anchor": dict(anchor),
        }
    requested_budget = _positive_int(values.get("remaining_budget_tokens"), "remaining_budget_tokens")
    if requested_budget > trusted_max_tokens:
        return {"state": "BLOCKED", "code": "REHYDRATION_BUDGET_UNTRUSTED", "outputs": {"loaded": []}}
    budget = requested_budget
    loaded: list[dict[str, Any]] = []
    missing: list[str] = []
    used = 0
    for source_id in requested_ids:
        item = by_id.get(source_id)
        if item is None:
            missing.append(source_id)
            continue
        content = item["content"]
        tokens = int(item["tokens"])
        if used + tokens > budget:
            return {
                "state": "BLOCKED",
                "code": "REHYDRATION_BUDGET_EXCEEDED",
                "outputs": {"loaded": loaded, "deferred_source_id": source_id, "used_tokens": used},
            }
        used += tokens
        loaded.append(
            {
                "source_id": source_id,
                "content": content,
                "content_digest": item["content_digest"],
                "package_version": package_version,
                "anchor": item["anchor"],
                "tokens": tokens,
            }
        )
    return {
        "state": "PARTIAL" if missing else "SUCCEEDED",
        "code": "REHYDRATION_SOURCE_MISSING" if missing else "CONTEXT_REHYDRATED",
        "outputs": {"loaded": loaded, "missing_source_ids": missing, "used_tokens": used, "catalog_digest": trusted.get("catalog_digest"), "load_digest": _digest(loaded)},
    }


def operate_project_memory(request: Mapping[str, Any]) -> dict[str, Any]:
    """Plan against a trusted snapshot without claiming an unperformed persistent effect."""

    values = _inputs(request)
    if {
        "items",
        "tenant_id",
        "project_id",
        "actor_id",
        "authorized_tools",
        "permissions",
        "authorized_operations",
        "policy",
        "consent",
        "authorization",
        "override",
        "receipt",
        "receipts",
    } & set(values):
        return {"state": "BLOCKED", "code": "MEMORY_AUTHORITY_INPUT_UNTRUSTED", "outputs": {"external_execution": "NOT_RUN"}}
    operation_value = values.get("operation", "query")
    if not isinstance(operation_value, str):
        raise ContextContractError("memory operation must be a string")
    operation = operation_value.lower()
    if operation not in {"write", "query", "delete"}:
        raise ContextContractError("memory operation must be write, query, or delete")
    tenant_id_value = request.get("tenant_id")
    project_id_value = request.get("project_id")
    actor_id_value = request.get("actor_id")
    if not all(isinstance(value, str) and value for value in (tenant_id_value, project_id_value, actor_id_value)):
        return {"state": "BLOCKED", "code": "PROJECT_MEMORY_SNAPSHOT_UNAVAILABLE", "outputs": {"external_execution": "NOT_RUN"}}
    tenant_id = str(tenant_id_value)
    project_id = str(project_id_value)
    actor_id = str(actor_id_value)
    branch_value = values.get("branch", "main")
    if not isinstance(branch_value, str) or not branch_value or len(branch_value.encode("utf-8")) > 256:
        raise ContextContractError("memory branch must be a bounded non-empty string")
    branch = branch_value
    trusted = _trusted_mapping(request, "capabilities", "project_memory_snapshot")
    if (
        trusted is None
        or trusted.get("verified") is not True
        or str(trusted.get("tenant_id", "")) != tenant_id
        or str(trusted.get("project_id", "")) != project_id
        or str(trusted.get("actor_id", "")) != actor_id
        or not actor_id
        or str(trusted.get("branch", "")) != branch
    ):
        return {"state": "BLOCKED", "code": "PROJECT_MEMORY_SNAPSHOT_UNAVAILABLE", "outputs": {"external_execution": "NOT_RUN"}}
    allowed_values = _sequence(trusted.get("allowed_operations", []), "project_memory_snapshot.allowed_operations", maximum=3)
    if any(not isinstance(item, str) for item in allowed_values):
        raise ContextContractError("project memory allowed operations must be strings")
    normalized_allowed = [item.lower() for item in allowed_values]
    allowed_operations = set(normalized_allowed)
    if (
        len(allowed_operations) != len(normalized_allowed)
        or allowed_operations - {"write", "query", "delete"}
        or operation not in allowed_operations
    ):
        return {"state": "BLOCKED", "code": "PROJECT_MEMORY_OPERATION_DENIED", "outputs": {"external_execution": "NOT_RUN"}}
    raw_items = _sequence(trusted.get("items", []), "project_memory_snapshot.items", maximum=_MAX_CONTEXT_ITEMS)
    _bounded_json(raw_items, "project_memory_snapshot.items")
    trusted_limit = _positive_int(trusted.get("max_results", 100), "project_memory_snapshot.max_results", maximum=100)
    snapshot_binding = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "actor_id": actor_id,
        "branch": branch,
        "allowed_operations": sorted(allowed_operations),
        "items": raw_items,
        "max_results": trusted_limit,
    }
    if trusted.get("snapshot_digest") != _digest(snapshot_binding):
        return {"state": "BLOCKED", "code": "PROJECT_MEMORY_SNAPSHOT_DIGEST_MISMATCH", "outputs": {"external_execution": "NOT_RUN"}}
    scoped: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise ContextContractError(f"project memory item {index} must be an object")
        memory_id_value = raw.get("memory_id")
        if (
            not isinstance(memory_id_value, str)
            or not memory_id_value
            or len(memory_id_value.encode("utf-8")) > 256
            or memory_id_value in identities
        ):
            raise ContextContractError("project memory IDs must be non-empty and unique")
        memory_id = memory_id_value
        identities.add(memory_id)
        if "tenant_id" in raw and str(raw.get("tenant_id")) != tenant_id:
            raise ContextContractError("project memory item contradicts the trusted tenant scope")
        if "project_id" in raw and str(raw.get("project_id")) != project_id:
            raise ContextContractError("project memory item contradicts the trusted project scope")
        if "branch" in raw and str(raw.get("branch")) != branch:
            raise ContextContractError("project memory item contradicts the trusted branch scope")
        item = dict(raw)
        item["tenant_id"] = tenant_id
        item["project_id"] = project_id
        item["actor_id"] = actor_id
        item["branch"] = branch
        item["version"] = _bounded_int(item.get("version", 0), "memory.version", minimum=0, maximum=1_000_000_000)
        item["source_digest"] = _require_sha256_digest(item.get("source_digest"), "memory.source_digest")
        if not isinstance(item.get("source_anchor"), Mapping) or not item.get("source_anchor"):
            raise ContextContractError("memory.source_anchor must be an object")
        _bounded_json(item.get("source_anchor"), "memory.source_anchor", maximum_bytes=64 * 1024)
        status = item.get("status", "CURRENT")
        if not isinstance(status, str) or status.upper() not in {"CURRENT", "DELETED", "SUPERSEDED"}:
            raise ContextContractError("memory.status is invalid")
        item["status"] = status.upper()
        _bounded_json(item, "project memory item", maximum_bytes=256 * 1024)
        scoped.append(item)
    if operation == "write":
        candidate = values.get("candidate")
        if not isinstance(candidate, Mapping) or not candidate.get("source_anchor"):
            return {"state": "BLOCKED", "code": "MEMORY_PROVENANCE_REQUIRED", "outputs": {"items": scoped}}
        if {
            "tenant_id",
            "project_id",
            "actor_id",
            "version",
            "status",
            "permission",
            "permissions",
            "authorization",
            "authorized",
            "approved",
            "receipt",
            "receipts",
            "persisted",
            "external_execution",
        } & set(candidate):
            return {"state": "BLOCKED", "code": "MEMORY_CANDIDATE_AUTHORITY_UNTRUSTED", "outputs": {"external_execution": "NOT_RUN"}}
        key_value = candidate.get("key")
        if (
            not isinstance(key_value, str)
            or not key_value
            or len(key_value.encode("utf-8")) > 512
            or not isinstance(candidate.get("source_anchor"), Mapping)
            or not candidate.get("source_anchor")
            or "source_digest" not in candidate
        ):
            return {"state": "BLOCKED", "code": "MEMORY_PROVENANCE_REQUIRED", "outputs": {"external_execution": "NOT_RUN"}}
        key = key_value
        _bounded_json(candidate.get("source_anchor"), "memory candidate source_anchor", maximum_bytes=64 * 1024)
        _require_sha256_digest(candidate.get("source_digest"), "memory candidate source_digest")
        _bounded_json(candidate, "memory candidate", maximum_bytes=256 * 1024)
        version = 1 + max((int(item["version"]) for item in scoped if item.get("key") == key), default=0)
        planned = {**dict(candidate), "tenant_id": tenant_id, "project_id": project_id, "actor_id": actor_id, "branch": branch, "version": version, "status": "PLANNED"}
        planned["memory_plan_digest"] = _digest(planned)
        return {"state": "PARTIAL", "code": "PROJECT_MEMORY_WRITE_PLANNED", "outputs": {"item": planned, "persisted": False, "external_execution": "NOT_RUN"}}
    if operation == "delete":
        source_digest = _require_sha256_digest(values.get("source_digest"), "source_digest")
        affected = [item for item in scoped if item.get("source_digest") == source_digest]
        return {
            "state": "PARTIAL",
            "code": "PROJECT_MEMORY_DELETION_PLANNED",
            "outputs": {"affected_ids": sorted(str(item.get("memory_id")) for item in affected), "propagation_complete": False, "external_execution": "NOT_RUN"},
        }
    query = str(values.get("query", "")).casefold()
    if len(query.encode("utf-8")) > 16 * 1024:
        raise ContextContractError("memory query exceeds the bounded length")
    terms = set(query.split())
    visible = [item for item in scoped if item.get("status", "CURRENT") != "DELETED"]
    for item in visible:
        item["score"] = len(terms & set(str(item.get("value", "")).casefold().split())) / max(1, len(terms))
    visible.sort(key=lambda item: (-float(item["score"]), -int(item.get("version", 0)), str(item.get("memory_id", ""))))
    requested_limit = _positive_int(values.get("limit", min(20, trusted_limit)), "limit", maximum=100)
    if requested_limit > trusted_limit:
        return {"state": "BLOCKED", "code": "PROJECT_MEMORY_LIMIT_UNTRUSTED", "outputs": {"external_execution": "NOT_RUN"}}
    return {
        "state": "PARTIAL",
        "code": "PROJECT_MEMORY_QUERY_PROJECTED",
        "outputs": {"results": visible[:requested_limit], "scope": {"tenant_id": tenant_id, "project_id": project_id, "actor_id": actor_id, "branch": branch}, "snapshot_digest": trusted.get("snapshot_digest"), "persistent_read_performed": False, "external_execution": "NOT_RUN"},
    }


def verify_context_integrity(request: Mapping[str, Any]) -> dict[str, Any]:
    """Compare typed critical facts exactly, including negation and numeric values."""

    values = _inputs(request)
    before = _sequence(values.get("before", []), "inputs.before", maximum=_MAX_CONTEXT_ITEMS)
    after = _sequence(values.get("after", []), "inputs.after", maximum=_MAX_CONTEXT_ITEMS)
    _bounded_json(before, "inputs.before")
    _bounded_json(after, "inputs.after")
    if not before:
        report = {
            "passed": False,
            "expected_count": 0,
            "retained_count": 0,
            "retention_ratio": 0.0,
            "missing_fact_ids": [],
            "unexpected_fact_ids": sorted(
                str(item.get("fact_id", "")) for item in after if isinstance(item, Mapping)
            ),
            "changed_facts": [],
            "action": "BLOCK_AND_ESTABLISH_BASELINE",
        }
        report["report_digest"] = _digest(report)
        return {
            "state": "BLOCKED",
            "code": "CONTEXT_INTEGRITY_BASELINE_EMPTY",
            "outputs": report,
        }

    def keyed(items: list[Any], field: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise ContextContractError(f"{field}[{index}] must be an object")
            _bounded_json(item, f"{field}[{index}]", maximum_bytes=64 * 1024)
            fact_id = str(item.get("fact_id", ""))
            if not fact_id or fact_id in result:
                raise ContextContractError(f"{field} has a missing or duplicate fact_id")
            negated = item.get("negated", False)
            if not isinstance(negated, bool):
                raise ContextContractError(f"{field}[{index}].negated must be a boolean")
            version = item.get("version")
            if version is not None:
                _bounded_int(version, f"{field}[{index}].version", minimum=0, maximum=1_000_000_000)
            result[fact_id] = {
                "type": str(item.get("type", "fact")),
                "value": item.get("value"),
                "negated": negated,
                "permission": item.get("permission"),
                "version": version,
                "source_digest": item.get("source_digest"),
            }
        return result

    expected = keyed(before, "before")
    observed = keyed(after, "after")
    missing = sorted(set(expected) - observed.keys())
    unexpected = sorted(set(observed) - expected.keys())
    changed = [
        {"fact_id": fact_id, "before": expected[fact_id], "after": observed[fact_id]}
        for fact_id in sorted(set(expected) & observed.keys())
        if expected[fact_id] != observed[fact_id]
    ]
    passed = not missing and not unexpected and not changed
    report = {
        "passed": passed,
        "expected_count": len(expected),
        "retained_count": len(expected) - len(missing) - len(changed),
        "retention_ratio": 1.0 if not expected else (len(expected) - len(missing) - len(changed)) / len(expected),
        "missing_fact_ids": missing,
        "unexpected_fact_ids": unexpected,
        "changed_facts": changed,
        "action": "CONTINUE" if passed else "BLOCK_AND_REHYDRATE_OR_ROLLBACK",
    }
    report["report_digest"] = _digest(report)
    return {
        "state": "SUCCEEDED" if passed else "BLOCKED",
        "code": "CONTEXT_INTEGRITY_PASSED" if passed else "CONTEXT_INTEGRITY_FAILED",
        "outputs": report,
    }
