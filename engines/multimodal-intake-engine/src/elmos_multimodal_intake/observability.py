"""Content-minimized observability, cost, and machine-wall-clock ETA logic."""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any


class ObservabilityContractError(ValueError):
    """Raised when usage or telemetry input is unsafe or incomplete."""


_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|token|authorization|cookie|api[_-]?key|"
    r"raw[_-]?(?:text|content|bytes)|prompt|message|body|payload|query|"
    r"document|source[_-]?content|input|output)",
    re.I,
)
_SENSITIVE_VALUE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"(?:postgres|mysql|mongodb|redis)://[^\s/:]+:[^\s@]+@|"
    r"(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"(?:sk|rk|pk)-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    re.I,
)
_ALLOWED_LABELS = frozenset({"stage", "provider", "file_type", "status", "error_code", "tenant_tier", "region"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]*")
_EVENT_TYPE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*")
_MAX_REDACTION_DEPTH = 64
_MAX_REDACTION_NODES = 100_000
_MAX_OBSERVABLE_STRING_BYTES = 8_192
_REDACTED_TEXT_MARKER = "[REDACTED_UNAPPROVED_TEXT]"


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
        raise ObservabilityContractError("value is not finite canonical JSON") from exc


def _digest(value: Any) -> str:
    data = value if isinstance(value, bytes) else _canonical(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _inputs(request: Mapping[str, Any]) -> Mapping[str, Any]:
    value = request.get("inputs")
    if not isinstance(value, Mapping):
        raise ObservabilityContractError("inputs must be an object")
    return value


def _sequence(value: Any, field: str, *, maximum: int = 100_000) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ObservabilityContractError(f"{field} must be an array")
    if len(value) > maximum:
        raise ObservabilityContractError(f"{field} exceeds the bounded item limit")
    return list(value)


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ObservabilityContractError(f"{field} must be an exact decimal") from exc
    if not result.is_finite() or result < 0:
        raise ObservabilityContractError(f"{field} must be finite and non-negative")
    return result


def _finite_float(value: Any, field: str, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ObservabilityContractError(f"{field} must be a finite number") from exc
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise ObservabilityContractError(f"{field} is outside its allowed finite range")
    return result


def _trusted_policy(request: Mapping[str, Any]) -> Mapping[str, Any] | None:
    policy = request.get("policy", {})
    if not isinstance(policy, Mapping):
        raise ObservabilityContractError("policy must be an object")
    observability = policy.get("observability")
    if observability is None:
        return None
    if not isinstance(observability, Mapping):
        raise ObservabilityContractError("policy.observability must be an object")
    return observability


def _trusted_collection(
    policy: Mapping[str, Any],
    values: Mapping[str, Any],
    field: str,
) -> list[Any] | None:
    items = _sequence(values.get(field, []), f"inputs.{field}", maximum=100_000)
    expected = policy.get(f"{field}_digest")
    if not isinstance(expected, str) or expected != _digest(items):
        return None
    return items


def estimate_processing_cost_eta(request: Mapping[str, Any]) -> dict[str, Any]:
    """Estimate machine wall-clock ETA and exact-decimal stage/provider cost."""

    values = _inputs(request)
    policy = _trusted_policy(request)
    if policy is None:
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_ESTIMATION_POLICY_REQUIRED",
            "outputs": {"external_evidence": "NOT_RUN"},
        }
    stages = _sequence(values.get("stages", []), "inputs.stages", maximum=1_000)
    if not stages:
        return {"state": "BLOCKED", "code": "ESTIMATION_STAGES_REQUIRED", "outputs": {}}
    history = _trusted_collection(policy, values, "history")
    prices = _trusted_collection(policy, values, "prices")
    calibration_version = policy.get("calibration_version")
    if history is None or prices is None or not isinstance(calibration_version, str) or not calibration_version:
        return {
            "state": "BLOCKED",
            "code": "ESTIMATION_INPUT_PROVENANCE_UNVERIFIED",
            "outputs": {"history_verified": history is not None, "prices_verified": prices is not None},
        }
    history_by_key: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for raw in history:
        if not isinstance(raw, Mapping):
            raise ObservabilityContractError("history rows must be objects")
        elapsed = _finite_float(raw.get("machine_wall_clock_seconds"), "history duration")
        key = (str(raw.get("stage")), str(raw.get("provider", "local")), str(raw.get("file_type", "unknown")))
        history_by_key[key].append(elapsed)
    price_by_key: dict[tuple[str, str], tuple[Decimal, str]] = {}
    for raw in prices:
        if not isinstance(raw, Mapping):
            raise ObservabilityContractError("price rows must be objects")
        price_key = (str(raw.get("provider")), str(raw.get("unit")))
        currency = str(raw.get("currency", ""))
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ObservabilityContractError("price currency must be a three-letter uppercase code")
        if price_key in price_by_key:
            raise ObservabilityContractError("duplicate provider price key")
        price_by_key[price_key] = (
            _decimal(raw.get("price_per_unit"), "price_per_unit"),
            currency,
        )
    stage_estimates: list[dict[str, Any]] = []
    currencies: set[str] = set()
    total_cost = Decimal("0")
    completion_p50: dict[str, float] = {}
    completion_p95: dict[str, float] = {}
    stage_ids: set[str] = set()
    for index, raw in enumerate(stages):
        if not isinstance(raw, Mapping):
            raise ObservabilityContractError(f"stages[{index}] must be an object")
        stage = str(raw.get("stage", ""))
        stage_id = str(raw.get("stage_id", stage))
        if not stage or not stage_id or stage_id in stage_ids:
            raise ObservabilityContractError("each stage and stage_id must be non-empty and unique")
        stage_ids.add(stage_id)
        provider = str(raw.get("provider", "local"))
        file_type = str(raw.get("file_type", "unknown"))
        key = (stage, provider, file_type)
        samples = sorted(history_by_key.get(key, []))
        progress = _finite_float(raw.get("progress", 0.0), "stage progress", maximum=1.0)
        elapsed = _finite_float(raw.get("elapsed_machine_seconds", 0.0), "elapsed machine seconds")
        if samples:
            p50 = statistics.median(samples)
            p95 = samples[min(len(samples) - 1, math.ceil(len(samples) * 0.95) - 1)]
            confidence = "CALIBRATED"
        else:
            declared = _finite_float(raw.get("declared_upper_bound_seconds", 0.0), "declared upper bound")
            if declared <= 0:
                return {
                    "state": "BLOCKED",
                    "code": "ETA_HISTORY_AND_BOUND_UNAVAILABLE",
                    "outputs": {"stage": stage, "machine_wall_clock": True},
                }
            p50, p95, confidence = declared * 0.6, declared, "COLD_START_WIDE_INTERVAL"
        remaining = max(0.0, (elapsed / progress - elapsed) if progress > 0 else p50)
        remaining_p95 = max(remaining, p95 * (1.0 - progress))
        quantity = _decimal(raw.get("quantity", 0), "quantity")
        unit = str(raw.get("unit", "none"))
        pricing = price_by_key.get((provider, unit))
        if quantity > 0 and pricing is None:
            return {
                "state": "BLOCKED",
                "code": "PROVIDER_PRICE_REQUIRED",
                "outputs": {"provider": provider, "unit": unit},
            }
        unit_price, currency = pricing or (Decimal("0"), str(policy.get("default_currency", "USD")))
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ObservabilityContractError("default currency must be a three-letter uppercase code")
        currencies.add(currency)
        cost = (quantity * unit_price).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        total_cost += cost
        raw_dependencies = raw.get("depends_on", [stage_estimates[-1]["stage_id"]] if stage_estimates else [])
        dependencies = [str(item) for item in _sequence(raw_dependencies, "stage.depends_on", maximum=1_000)]
        if len(set(dependencies)) != len(dependencies) or any(item not in completion_p50 for item in dependencies):
            raise ObservabilityContractError("stage dependencies must be unique earlier stage IDs")
        starts_p50 = max((completion_p50[item] for item in dependencies), default=0.0)
        starts_p95 = max((completion_p95[item] for item in dependencies), default=0.0)
        completion_p50[stage_id] = starts_p50 + remaining
        completion_p95[stage_id] = starts_p95 + remaining_p95
        stage_estimates.append(
            {
                "stage_id": stage_id,
                "stage": stage,
                "provider": provider,
                "file_type": file_type,
                "progress": progress,
                "remaining_seconds_p50": round(remaining, 6),
                "remaining_seconds_p95": round(remaining_p95, 6),
                "confidence": confidence,
                "cost": format(cost, "f"),
                "currency": currency,
                "quantity": format(quantity, "f"),
                "unit": unit,
                "depends_on": dependencies,
            }
        )
    if len(currencies) > 1:
        return {"state": "BLOCKED", "code": "COST_CURRENCY_RECONCILIATION_REQUIRED", "outputs": {"currencies": sorted(currencies)}}
    report = {
        "eta_basis": "MACHINE_WALL_CLOCK_SECONDS",
        "remaining_seconds_p50": round(max(completion_p50.values(), default=0.0), 6),
        "remaining_seconds_p95": round(max(completion_p95.values(), default=0.0), 6),
        "stages": stage_estimates,
        "estimated_cost": format(total_cost, "f"),
        "currency": next(iter(currencies), str(values.get("currency", "USD"))),
        "provider_actuals_reconciled": bool(policy.get("provider_actuals_reconciled", False)),
        "calibration_version": calibration_version,
        "history_digest": policy["history_digest"],
        "prices_digest": policy["prices_digest"],
    }
    report["estimate_digest"] = _digest(report)
    return {"state": "SUCCEEDED", "code": "PROCESSING_COST_ETA_ESTIMATED", "outputs": report}


def _strict_identifier(
    value: Any,
    field: str,
    *,
    maximum_bytes: int = 128,
    pattern: re.Pattern[str] = _IDENTIFIER,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ObservabilityContractError(f"{field} must be an exact non-blank identifier")
    if len(value.encode("utf-8")) > maximum_bytes or pattern.fullmatch(value) is None:
        raise ObservabilityContractError(f"{field} is outside the strict identifier bounds")
    if _SENSITIVE_VALUE.search(value):
        raise ObservabilityContractError(f"{field} contains sensitive material")
    return value


def _redact(
    value: Any,
    *,
    key: str = "",
    depth: int = 0,
    budget: list[int] | None = None,
) -> Any:
    if budget is None:
        budget = [_MAX_REDACTION_NODES]
    if depth > _MAX_REDACTION_DEPTH:
        raise ObservabilityContractError("observable attributes exceed the redaction depth limit")
    budget[0] -= 1
    if budget[0] < 0:
        raise ObservabilityContractError("observable attributes exceed the redaction node limit")
    if _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        redacted_key_index = 0
        for child_key, child_value in value.items():
            if not isinstance(child_key, str) or not child_key:
                raise ObservabilityContractError("observable attribute keys must be non-empty strings")
            if len(child_key.encode("utf-8")) > 256:
                raise ObservabilityContractError("observable attribute key exceeds the bounded limit")
            if _SENSITIVE_VALUE.search(child_key):
                redacted_key_index += 1
                safe_key = f"redacted_key_{redacted_key_index}"
            else:
                safe_key = child_key
            if safe_key in redacted:
                raise ObservabilityContractError("observable attribute keys collide after redaction")
            redacted[safe_key] = _redact(
                child_value,
                key=child_key,
                depth=depth + 1,
                budget=budget,
            )
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth=depth + 1, budget=budget) for item in value]
    if isinstance(value, str):
        if len(value.encode("utf-8")) > _MAX_OBSERVABLE_STRING_BYTES:
            raise ObservabilityContractError("observable string exceeds the bounded redaction limit")
        # Attribute strings are untrusted and can contain prose or a secret
        # shape that no finite detector knows about. Keep useful numeric and
        # boolean telemetry, but default-deny every untyped string. Identifiers
        # needed for correlation are modeled as strict top-level/label fields.
        return _REDACTED_TEXT_MARKER
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObservabilityContractError("observable number must be finite")
        return value
    raise ObservabilityContractError("observable attribute type is unsupported")


def build_multimodal_observability(request: Mapping[str, Any]) -> dict[str, Any]:
    """Create a bounded, redacted trace/metric projection."""

    values = _inputs(request)
    policy = _trusted_policy(request)
    if policy is None:
        return {
            "state": "BLOCKED",
            "code": "TRUSTED_OBSERVABILITY_POLICY_REQUIRED",
            "outputs": {"external_evidence": "NOT_RUN"},
        }
    events = _sequence(values.get("events", []), "inputs.events", maximum=100_000)
    trace_id = _strict_identifier(
        request.get("trace_id") or values.get("trace_id"),
        "trace_id",
        maximum_bytes=128,
    )
    safe_events: list[dict[str, Any]] = []
    label_values: dict[str, set[str]] = defaultdict(set)
    stages: set[str] = set()
    event_ids: set[str] = set()
    redaction_budget = [_MAX_REDACTION_NODES]
    for index, raw in enumerate(events):
        if not isinstance(raw, Mapping):
            raise ObservabilityContractError(f"events[{index}] must be an object")
        event_id = _strict_identifier(
            raw.get("event_id"), f"events[{index}].event_id", maximum_bytes=128
        )
        if event_id in event_ids:
            raise ObservabilityContractError("event_id must be unique within a trace")
        event_type = _strict_identifier(
            raw.get("event_type"),
            f"events[{index}].event_type",
            maximum_bytes=96,
            pattern=_EVENT_TYPE,
        )
        raw_parent = raw.get("parent_event_id")
        parent_event_id = None
        if raw_parent is not None:
            parent_event_id = _strict_identifier(
                raw_parent,
                f"events[{index}].parent_event_id",
                maximum_bytes=128,
            )
            if parent_event_id not in event_ids:
                raise ObservabilityContractError(
                    "parent_event_id must reference an earlier event in the same trace"
                )
        labels = raw.get("labels", {})
        if not isinstance(labels, Mapping):
            raise ObservabilityContractError("event labels must be an object")
        if any(not isinstance(key, str) for key in labels):
            raise ObservabilityContractError("event label keys must be strings")
        unknown = set(labels) - _ALLOWED_LABELS
        if unknown:
            return {
                "state": "BLOCKED",
                "code": "OBSERVABILITY_HIGH_CARDINAL_LABEL_BLOCKED",
                "outputs": {"unsupported_label_count": len(unknown)},
            }
        safe_labels: dict[str, str] = {}
        for key, value in labels.items():
            normalized = _strict_identifier(
                value,
                f"events[{index}].labels.{key}",
                maximum_bytes=128,
            )
            label_values[key].add(normalized)
            safe_labels[key] = normalized
        stage = safe_labels.get("stage")
        if stage:
            stages.add(stage)
        event_ids.add(event_id)
        safe_events.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "trace_id": trace_id,
                "parent_event_id": parent_event_id,
                "labels": safe_labels,
                "attributes": _redact(raw.get("attributes", {}), budget=redaction_budget),
            }
        )
    cardinality_limit = policy.get("label_cardinality_limit", 1_000)
    if (
        isinstance(cardinality_limit, bool)
        or not isinstance(cardinality_limit, int)
        or not 1 <= cardinality_limit <= 10_000
    ):
        raise ObservabilityContractError("trusted label cardinality limit is invalid")
    exceeded = {key: len(items) for key, items in label_values.items() if len(items) > cardinality_limit}
    if exceeded:
        return {"state": "BLOCKED", "code": "OBSERVABILITY_CARDINALITY_LIMIT", "outputs": {"exceeded": exceeded}}
    required_values = _sequence(policy.get("required_stages", []), "policy.observability.required_stages", maximum=1_000)
    required_stages = {
        _strict_identifier(
            item,
            f"policy.observability.required_stages[{index}]",
            maximum_bytes=128,
        )
        for index, item in enumerate(required_values)
    }
    if not required_stages:
        return {"state": "BLOCKED", "code": "OBSERVABILITY_REQUIRED_STAGES_MISSING", "outputs": {}}
    missing_stages = sorted(required_stages - stages)
    report = {
        "trace_id": trace_id,
        "events": safe_events,
        "missing_stages": missing_stages,
        "label_cardinality": {key: len(items) for key, items in sorted(label_values.items())},
        "content_minimized": True,
        "redaction_applied": True,
        "secrets_redacted": "DEFAULT_DENY_UNAPPROVED_TEXT",
        "attribute_string_policy": "REDACT_ALL_UNTYPED_STRINGS",
        "policy_version": _strict_identifier(
            policy.get("policy_version"), "policy.observability.policy_version", maximum_bytes=128
        ),
    }
    report["trace_digest"] = _digest(report)
    return {
        "state": "PARTIAL" if missing_stages else "SUCCEEDED",
        "code": "TRACE_STAGE_GAP" if missing_stages else "MULTIMODAL_TRACE_CREATED",
        "outputs": report,
    }
