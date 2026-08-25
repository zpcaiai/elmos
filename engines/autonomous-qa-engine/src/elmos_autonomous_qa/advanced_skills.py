"""Bounded local contracts for the advanced Autonomous QA Skills.

These handlers validate and derive deterministic plans or local evaluations.
They never execute project code, acquire infrastructure, persist checkpoints,
accept caller-supplied trust, sign evidence, or authorize a governed action.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Final

from .canonical import normalize_relative_path
from .contracts import (
    ContractError,
    digest_json,
    require_resource_id,
    require_text,
    strict_json,
)


_DIGEST: Final = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_PRIORITY: Final = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_SEVERITY: Final = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_TERMINAL: Final = ("PASSED", "FAILED", "BLOCKED", "CANCELLED", "TIMED_OUT")


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise ContractError(f"{field} must be an exact string-keyed object")
    return value


def _objects(
    value: Any, field: str, *, allow_empty: bool = False
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a non-empty object array")
    if any(not isinstance(item, Mapping) for item in value):
        raise ContractError(f"{field} must contain only objects")
    return list(value)


def _strings(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a non-empty string array")
    if any(not isinstance(item, str) for item in value):
        raise ContractError(f"{field} must contain only strings")
    if len(set(value)) != len(value):
        raise ContractError(f"{field} may not contain duplicates")
    return list(value)


def _ids(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    return [
        require_resource_id(item, f"{field}[]")
        for item in _strings(value, field, allow_empty=allow_empty)
    ]


def _exact(
    value: Mapping[str, Any],
    field: str,
    *,
    allowed: set[str] | frozenset[str],
    required: set[str] | frozenset[str] = frozenset(),
) -> None:
    unexpected = sorted(set(value).difference(allowed))
    missing = sorted(set(required).difference(value))
    if unexpected:
        raise ContractError(f"{field} has unsupported fields: {unexpected}")
    if missing:
        raise ContractError(f"{field} is missing required fields: {missing}")


def _validated_runtime_context(
    request: Mapping[str, Any], *, require_actor: bool = False
) -> Mapping[str, Any]:
    raw = request.get("_runtime_context")
    if raw is None:
        if require_actor:
            raise ContractError("_runtime_context is required")
        return MappingProxyType({})
    context = _object(raw, "_runtime_context")
    _exact(
        context,
        "_runtime_context",
        allowed={
            "tenant_id",
            "project_id",
            "actor_id",
            "request_id",
            "idempotency_key",
        },
        required={
            "tenant_id",
            "project_id",
            "actor_id",
            "request_id",
            "idempotency_key",
        },
    )
    for field in ("tenant_id", "project_id", "actor_id", "request_id"):
        value = context.get(field)
        if value is not None:
            require_resource_id(value, f"runtime.{field}")
    idempotency_key = context.get("idempotency_key")
    if idempotency_key is not None:
        require_text(idempotency_key, "runtime.idempotency_key", maximum=200)
    if require_actor and context.get("actor_id") is None:
        raise ContractError("runtime.actor_id is required")
    return context


def _integer(
    value: Any, field: str, *, minimum: int = 0, maximum: int = 1_000_000
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(
            f"{field} must be an integer from {minimum} through {maximum}"
        )
    return value


def _number(
    value: Any,
    field: str,
    *,
    minimum: float = 0.0,
    maximum: float = 1_000_000_000.0,
) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not minimum <= float(value) <= maximum
    ):
        raise ContractError(
            f"{field} must be a finite number from {minimum} through {maximum}"
        )
    return float(value)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field} must be boolean")
    return value


def _sha256(value: Any, field: str) -> str:
    text = require_text(value, field, maximum=71)
    if _DIGEST.fullmatch(text) is None:
        raise ContractError(f"{field} must be an exact SHA-256 digest")
    return text[7:] if text.startswith("sha256:") else text


def _path(value: Any, field: str) -> str:
    try:
        return normalize_relative_path(require_text(value, field, maximum=1024))
    except ValueError as exc:
        raise ContractError(f"{field} must be a canonical repository-relative path") from exc


def _timestamp(value: Any, field: str) -> datetime:
    text = require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError as exc:
        raise ContractError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} must include a timezone")
    return parsed


def _topological_order(
    node_ids: Sequence[str], dependencies: Mapping[str, Sequence[str]], field: str
) -> list[str]:
    known = set(node_ids)
    unknown = sorted(
        {dependency for values in dependencies.values() for dependency in values} - known
    )
    if unknown:
        raise ContractError(f"{field} references unknown nodes: {unknown}")
    indegree = {node_id: len(dependencies[node_id]) for node_id in node_ids}
    downstream: dict[str, list[str]] = defaultdict(list)
    for node_id, values in dependencies.items():
        for dependency in values:
            downstream[dependency].append(node_id)
    ready = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for child in sorted(downstream[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready = deque(sorted(ready))
    if len(ordered) != len(node_ids):
        raise ContractError(f"{field} contains a dependency cycle")
    return ordered


def _result(
    state: str,
    code: str,
    outputs: Mapping[str, Any],
    *,
    implementation_state: str = "LOCAL_VALIDATED",
) -> Mapping[str, Any]:
    return {
        "state": state,
        "code": code,
        "outputs": strict_json(outputs, "advanced Skill outputs", output=True),
        "implementation_state": implementation_state,
    }


def plan_distributed_execution(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build a typed, dependency-safe scheduler plan without executing it."""

    request = _object(inputs, "scheduler request")
    _exact(
        request,
        "scheduler request",
        allowed={
            "tasks",
            "workers",
            "capacity",
            "backpressure",
            "lease_seconds",
            "heartbeat_seconds",
            "checkpoint_interval_seconds",
            "_runtime_context",
        },
        required={
            "tasks",
            "capacity",
            "backpressure",
            "lease_seconds",
            "heartbeat_seconds",
            "checkpoint_interval_seconds",
        },
    )
    _validated_runtime_context(request)
    tasks = _objects(request.get("tasks"), "tasks")
    workers = _integer(request.get("workers", 1), "workers", minimum=1, maximum=256)
    capacity = _object(request.get("capacity"), "capacity")
    _exact(
        capacity,
        "capacity",
        allowed={"cpu_millis", "memory_mb", "gpu_count", "max_in_flight"},
        required={"cpu_millis", "memory_mb", "max_in_flight"},
    )
    available = {
        "cpu_millis": _integer(
            capacity.get("cpu_millis"), "capacity.cpu_millis", minimum=1
        ),
        "memory_mb": _integer(
            capacity.get("memory_mb"), "capacity.memory_mb", minimum=1
        ),
        "gpu_count": _integer(
            capacity.get("gpu_count", 0), "capacity.gpu_count", maximum=1024
        ),
        "max_in_flight": _integer(
            capacity.get("max_in_flight"),
            "capacity.max_in_flight",
            minimum=1,
            maximum=256,
        ),
    }
    backpressure = _object(request.get("backpressure"), "backpressure")
    _exact(
        backpressure,
        "backpressure",
        allowed={"max_queue_depth", "high_watermark"},
        required={"max_queue_depth", "high_watermark"},
    )
    max_queue = _integer(
        backpressure.get("max_queue_depth"),
        "backpressure.max_queue_depth",
        minimum=1,
        maximum=100_000,
    )
    high_watermark = _integer(
        backpressure.get("high_watermark"),
        "backpressure.high_watermark",
        minimum=1,
        maximum=max_queue,
    )
    lease_seconds = _integer(
        request.get("lease_seconds"), "lease_seconds", minimum=5, maximum=86_400
    )
    heartbeat_seconds = _integer(
        request.get("heartbeat_seconds"),
        "heartbeat_seconds",
        minimum=1,
        maximum=lease_seconds - 1,
    )
    checkpoint_seconds = _integer(
        request.get("checkpoint_interval_seconds"),
        "checkpoint_interval_seconds",
        minimum=1,
        maximum=lease_seconds,
    )
    task_by_id: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, list[str]] = {}
    for raw in tasks:
        _exact(
            raw,
            "task",
            allowed={
                "test_case_id",
                "priority",
                "dependency_ids",
                "environment_profile",
                "resources",
                "estimated_seconds",
            },
            required={
                "test_case_id",
                "priority",
                "dependency_ids",
                "environment_profile",
                "resources",
                "estimated_seconds",
            },
        )
        test_id = require_resource_id(raw.get("test_case_id"), "task.test_case_id")
        if test_id in task_by_id:
            raise ContractError(f"duplicate task test_case_id: {test_id}")
        priority = require_text(raw.get("priority"), "task.priority")
        if priority not in _PRIORITY:
            raise ContractError("task.priority must be P0, P1, P2, or P3")
        task_dependencies = _ids(
            raw.get("dependency_ids"), "task.dependency_ids", allow_empty=True
        )
        if test_id in task_dependencies:
            raise ContractError(f"task {test_id} may not depend on itself")
        resources = _object(raw.get("resources"), "task.resources")
        _exact(
            resources,
            "task.resources",
            allowed={"cpu_millis", "memory_mb", "gpu_count"},
            required={"cpu_millis", "memory_mb"},
        )
        requested = {
            "cpu_millis": _integer(
                resources.get("cpu_millis"), "task.resources.cpu_millis", minimum=1
            ),
            "memory_mb": _integer(
                resources.get("memory_mb"), "task.resources.memory_mb", minimum=1
            ),
            "gpu_count": _integer(
                resources.get("gpu_count", 0), "task.resources.gpu_count", maximum=1024
            ),
        }
        if any(requested[key] > available[key] for key in requested):
            raise ContractError(f"task {test_id} exceeds scheduler capacity")
        task_by_id[test_id] = {
            "test_case_id": test_id,
            "priority": priority,
            "dependency_ids": sorted(task_dependencies),
            "environment_profile": require_resource_id(
                raw.get("environment_profile"), "task.environment_profile"
            ),
            "resources": requested,
            "estimated_seconds": _number(
                raw.get("estimated_seconds"),
                "task.estimated_seconds",
                maximum=31_536_000,
            ),
        }
        dependencies[test_id] = task_dependencies
    if len(tasks) > max_queue:
        raise ContractError("task queue exceeds backpressure.max_queue_depth")
    topological = _topological_order(list(task_by_id), dependencies, "task graph")
    order_index = {node_id: index for index, node_id in enumerate(topological)}
    ordered_ids = sorted(
        topological,
        key=lambda node_id: (
            max(
                (order_index[dependency] for dependency in dependencies[node_id]),
                default=-1,
            ),
            _PRIORITY[task_by_id[node_id]["priority"]],
            order_index[node_id],
        ),
    )
    plan = {
        "tasks": [task_by_id[node_id] for node_id in ordered_ids],
        "workers": min(workers, available["max_in_flight"]),
        "capacity": available,
        "backpressure": {
            "max_queue_depth": max_queue,
            "high_watermark": high_watermark,
            "admission_above_high_watermark": "PAUSE",
        },
        "lease": {
            "duration_seconds": lease_seconds,
            "heartbeat_seconds": heartbeat_seconds,
            "expiry_outcome": "BLOCKED_RECONCILIATION_REQUIRED",
        },
        "fencing": {
            "monotonic_token_required": True,
            "stale_worker_results_rejected": True,
        },
        "checkpoint": {
            "interval_seconds": checkpoint_seconds,
            "content_digest_required": True,
            "resume_requires_same_plan_digest": True,
        },
        "terminal_completeness": {
            "required_states": list(_TERMINAL),
            "one_terminal_result_per_task": True,
            "missing_result_is_success": False,
        },
    }
    plan["plan_digest"] = digest_json(plan)
    return _result(
        "PARTIAL",
        "DISTRIBUTED_EXECUTION_PLAN_CREATED",
        {
            "scheduler_plan": plan,
            "queue_high_watermark_reached": len(tasks) >= high_watermark,
            "execution": "NOT_RUN",
            "lease_acquired": False,
            "terminal_results": "NOT_RUN",
        },
        implementation_state="EXTERNAL_ADAPTER_REQUIRED",
    )


def _compare_oracle(
    comparator: str, expected: Any, actual: Any, tolerance: float | None
) -> tuple[bool, Any]:
    if comparator == "equal":
        return expected == actual, None
    if comparator == "numeric-absolute":
        if (
            not isinstance(expected, (int, float))
            or isinstance(expected, bool)
            or not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or tolerance is None
        ):
            raise ContractError("numeric-absolute requires numeric values and tolerance")
        difference = abs(float(actual) - float(expected))
        return difference <= tolerance, difference
    if comparator == "numeric-relative":
        if (
            not isinstance(expected, (int, float))
            or isinstance(expected, bool)
            or not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or tolerance is None
        ):
            raise ContractError("numeric-relative requires numeric values and tolerance")
        denominator = max(abs(float(expected)), 1e-12)
        difference = abs(float(actual) - float(expected)) / denominator
        return difference <= tolerance, difference
    if comparator == "set-equal":
        if not isinstance(expected, list) or not isinstance(actual, list):
            raise ContractError("set-equal requires JSON arrays")
        expected_keys = sorted(digest_json(item) for item in expected)
        actual_keys = sorted(digest_json(item) for item in actual)
        return expected_keys == actual_keys, {
            "missing": sorted(set(expected_keys) - set(actual_keys)),
            "unexpected": sorted(set(actual_keys) - set(expected_keys)),
        }
    raise ContractError(f"unsupported oracle comparator: {comparator}")


def evaluate_oracle_evidence(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Evaluate typed local observations while retaining the trust boundary."""

    request = _object(inputs, "oracle request")
    _exact(
        request,
        "oracle request",
        allowed={"oracle", "observations", "_runtime_context"},
        required={"oracle", "observations"},
    )
    _validated_runtime_context(request)
    oracle = _object(request.get("oracle"), "oracle")
    _exact(
        oracle,
        "oracle",
        allowed={"oracle_id", "dimensions", "provenance"},
        required={"oracle_id", "dimensions", "provenance"},
    )
    oracle_id = require_resource_id(oracle.get("oracle_id"), "oracle.oracle_id")
    provenance = _object(oracle.get("provenance"), "oracle.provenance")
    _exact(
        provenance,
        "oracle.provenance",
        allowed={"source_id", "source_digest", "observed_at", "collector_id"},
        required={"source_id", "source_digest", "observed_at", "collector_id"},
    )
    normalized_provenance = {
        "source_id": require_resource_id(
            provenance.get("source_id"), "oracle.provenance.source_id"
        ),
        "source_digest": _sha256(
            provenance.get("source_digest"), "oracle.provenance.source_digest"
        ),
        "observed_at": require_text(
            provenance.get("observed_at"), "oracle.provenance.observed_at", maximum=64
        ),
        "collector_id": require_resource_id(
            provenance.get("collector_id"), "oracle.provenance.collector_id"
        ),
    }
    _timestamp(normalized_provenance["observed_at"], "oracle.provenance.observed_at")
    dimensions = _objects(oracle.get("dimensions"), "oracle.dimensions")
    observations = _objects(request.get("observations"), "observations")
    observed_by_name: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        _exact(
            observation,
            "observation",
            allowed={"name", "actual"},
            required={"name", "actual"},
        )
        name = require_resource_id(observation.get("name"), "observation.name")
        if name in observed_by_name:
            raise ContractError(f"duplicate observation dimension: {name}")
        observed_by_name[name] = observation
    evaluated: list[dict[str, Any]] = []
    dimension_names: set[str] = set()
    blockers: list[str] = []
    for dimension in dimensions:
        _exact(
            dimension,
            "oracle.dimension",
            allowed={"name", "expected", "comparator", "tolerance", "redact"},
            required={"name", "expected", "comparator"},
        )
        name = require_resource_id(dimension.get("name"), "oracle.dimension.name")
        if name in dimension_names:
            raise ContractError(f"duplicate oracle dimension: {name}")
        dimension_names.add(name)
        observation = observed_by_name.get(name)
        if observation is None:
            blockers.append(f"{name}:OBSERVATION_MISSING")
            continue
        comparator = require_text(
            dimension.get("comparator"), "oracle.dimension.comparator"
        )
        raw_tolerance = dimension.get("tolerance")
        tolerance = (
            _number(raw_tolerance, "oracle.dimension.tolerance", maximum=1_000_000)
            if raw_tolerance is not None
            else None
        )
        if comparator == "equal" and tolerance is not None:
            raise ContractError("equal comparator may not declare tolerance")
        if comparator == "numeric-relative" and tolerance is not None and tolerance > 1:
            raise ContractError("numeric-relative tolerance may not exceed 1")
        expected = strict_json(dimension.get("expected"), "oracle expected")
        actual = strict_json(observation.get("actual"), "oracle observation")
        passed, difference = _compare_oracle(comparator, expected, actual, tolerance)
        redact = _boolean(dimension.get("redact", False), "oracle.dimension.redact")
        item: dict[str, Any] = {
            "name": name,
            "comparator": comparator,
            "tolerance": tolerance,
            "passed": passed,
            "expected_digest": digest_json(expected),
            "actual_digest": digest_json(actual),
            "difference": difference,
            "redacted": redact,
        }
        if not redact:
            item["expected"] = expected
            item["actual"] = actual
        if not passed:
            blockers.append(f"{name}:ORACLE_MISMATCH")
        evaluated.append(item)
    unexpected = sorted(set(observed_by_name).difference(dimension_names))
    if unexpected:
        raise ContractError(f"observations contain undeclared dimensions: {unexpected}")
    manifest = {
        "oracle_id": oracle_id,
        "provenance": normalized_provenance,
        "dimensions": evaluated,
        "local_evaluation": "FAILED" if blockers else "PASSED",
        "quarantined": bool(blockers),
    }
    manifest["manifest_digest"] = digest_json(manifest)
    return _result(
        "FAILED" if blockers else "BLOCKED",
        "ORACLE_EVIDENCE_QUARANTINED"
        if blockers
        else "TRUSTED_EVIDENCE_ATTESTATION_REQUIRED",
        {
            "evidence_manifest": manifest,
            "observation_differences": evaluated,
            "blockers": blockers,
            "signature": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certified": False,
        },
    )


_FLAKE_FIELDS: Final = (
    "input_digest",
    "environment_digest",
    "time_bucket",
    "resource_digest",
    "dependency_digest",
    "seed",
    "order_digest",
    "product_digest",
    "test_digest",
)


def classify_flakiness(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Classify observed instability without re-running or hiding attempts."""

    request = _object(inputs, "flake request")
    _exact(
        request,
        "flake request",
        allowed={"attempts", "stability_window", "_runtime_context"},
        required={"attempts"},
    )
    _validated_runtime_context(request)
    attempts = _objects(request.get("attempts"), "attempts")
    window = _integer(
        request.get("stability_window", 3),
        "stability_window",
        minimum=1,
        maximum=100,
    )
    by_test: dict[str, list[dict[str, Any]]] = defaultdict(list)
    attempt_ids: set[str] = set()
    allowed = {
        "attempt_id",
        "test_case_id",
        "status",
        *_FLAKE_FIELDS,
    }
    for raw in attempts:
        _exact(
            raw,
            "attempt",
            allowed=allowed,
            required={"attempt_id", "test_case_id", "status", *_FLAKE_FIELDS},
        )
        attempt_id = require_resource_id(raw.get("attempt_id"), "attempt.attempt_id")
        if attempt_id in attempt_ids:
            raise ContractError(f"duplicate attempt_id: {attempt_id}")
        attempt_ids.add(attempt_id)
        status = require_text(raw.get("status"), "attempt.status").upper()
        if status not in _TERMINAL:
            raise ContractError("attempt.status must be a terminal status")
        normalized: dict[str, Any] = {
            "attempt_id": attempt_id,
            "test_case_id": require_resource_id(
                raw.get("test_case_id"), "attempt.test_case_id"
            ),
            "status": status,
            "seed": _integer(raw.get("seed"), "attempt.seed", maximum=2**31 - 1),
        }
        for field in _FLAKE_FIELDS:
            if field == "seed":
                continue
            normalized[field] = require_text(raw.get(field), f"attempt.{field}", maximum=256)
        by_test[normalized["test_case_id"]].append(normalized)
    profiles: list[dict[str, Any]] = []
    blockers: list[str] = []
    for test_id, observed in sorted(by_test.items()):
        statuses = [item["status"] for item in observed]
        changes = {
            field: len({item[field] for item in observed}) > 1 for field in _FLAKE_FIELDS
        }
        has_pass = "PASSED" in statuses
        has_nonpass = any(status != "PASSED" for status in statuses)
        variable = has_pass and has_nonpass
        if changes["input_digest"]:
            classification = "INCOMPARABLE_INPUT"
        elif any(
            changes[field]
            for field in (
                "environment_digest",
                "time_bucket",
                "resource_digest",
                "dependency_digest",
            )
        ):
            classification = "ENVIRONMENT_FLAKE" if variable else "STABLE"
        elif any(changes[field] for field in ("test_digest", "seed", "order_digest")):
            classification = "TEST_FLAKE" if variable else "STABLE"
        elif variable:
            classification = "PRODUCT_FLAKE"
        else:
            classification = "STABLE" if len(observed) >= 2 else "INSUFFICIENT_WINDOW"
        stable_passes = 0
        for status in reversed(statuses):
            if status != "PASSED":
                break
            stable_passes += 1
        isolated = classification.endswith("FLAKE") or classification in {
            "INCOMPARABLE_INPUT",
            "INSUFFICIENT_WINDOW",
        }
        release_eligible = isolated and stable_passes >= window and not changes["input_digest"]
        if isolated and not release_eligible:
            blockers.append(test_id)
        profiles.append(
            {
                "test_case_id": test_id,
                "classification": classification,
                "attempts": observed,
                "dimension_changes": changes,
                "isolation": "RELEASE_CANDIDATE"
                if release_eligible
                else "QUARANTINED"
                if isolated
                else "NONE",
                "stability_window_required": window,
                "consecutive_terminal_passes": stable_passes,
                "release_eligible": release_eligible,
            }
        )
    return _result(
        "PARTIAL" if blockers else "SUCCEEDED",
        "FLAKE_ISOLATION_REQUIRED" if blockers else "FLAKE_CLASSIFICATION_COMPLETE",
        {
            "profiles": profiles,
            "gate_blockers": blockers,
            "all_attempts_retained": True,
            "attempt_execution": "NOT_RUN",
            "automatic_quarantine_mutation": False,
        },
    )


def triage_advanced_defects(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Correlate failures and hypotheses while suppressing upstream cascades."""

    request = _object(inputs, "triage request")
    _exact(
        request,
        "triage request",
        allowed={"failures", "changes", "history", "hypotheses", "_runtime_context"},
        required={"failures", "hypotheses"},
    )
    _validated_runtime_context(request)
    failures = _objects(request.get("failures"), "failures")
    changes = _objects(request.get("changes", []), "changes", allow_empty=True)
    histories = _objects(request.get("history", []), "history", allow_empty=True)
    hypotheses = _objects(request.get("hypotheses"), "hypotheses")
    failure_by_id: dict[str, dict[str, Any]] = {}
    for raw in failures:
        _exact(
            raw,
            "failure",
            allowed={
                "failure_id",
                "test_case_id",
                "fingerprint",
                "severity",
                "owner",
                "changed_paths",
                "upstream_failure_ids",
                "reproduction_steps",
            },
            required={
                "failure_id",
                "test_case_id",
                "fingerprint",
                "severity",
                "changed_paths",
                "upstream_failure_ids",
                "reproduction_steps",
            },
        )
        failure_id = require_resource_id(raw.get("failure_id"), "failure.failure_id")
        if failure_id in failure_by_id:
            raise ContractError(f"duplicate failure_id: {failure_id}")
        severity = require_text(raw.get("severity"), "failure.severity").upper()
        if severity not in _SEVERITY:
            raise ContractError("failure.severity is invalid")
        failure_by_id[failure_id] = {
            "failure_id": failure_id,
            "test_case_id": require_resource_id(
                raw.get("test_case_id"), "failure.test_case_id"
            ),
            "fingerprint": require_text(
                raw.get("fingerprint"), "failure.fingerprint", maximum=512
            ),
            "severity": severity,
            "owner": require_resource_id(raw.get("owner"), "failure.owner")
            if raw.get("owner") is not None
            else None,
            "changed_paths": [
                _path(value, "failure.changed_paths[]")
                for value in _strings(
                    raw.get("changed_paths"), "failure.changed_paths", allow_empty=True
                )
            ],
            "upstream_failure_ids": _ids(
                raw.get("upstream_failure_ids"),
                "failure.upstream_failure_ids",
                allow_empty=True,
            ),
            "reproduction_steps": _strings(
                raw.get("reproduction_steps"), "failure.reproduction_steps"
            ),
        }
    for failure in failure_by_id.values():
        unknown = sorted(set(failure["upstream_failure_ids"]) - set(failure_by_id))
        if unknown or failure["failure_id"] in failure["upstream_failure_ids"]:
            raise ContractError(
                f"failure {failure['failure_id']} has invalid upstream references: {unknown}"
            )
    _topological_order(
        list(failure_by_id),
        {
            failure_id: value["upstream_failure_ids"]
            for failure_id, value in failure_by_id.items()
        },
        "failure graph",
    )
    change_records: list[dict[str, Any]] = []
    change_ids: set[str] = set()
    for raw in changes:
        _exact(
            raw,
            "change",
            allowed={"change_id", "path", "owner"},
            required={"change_id", "path", "owner"},
        )
        change_id = require_resource_id(raw.get("change_id"), "change.change_id")
        if change_id in change_ids:
            raise ContractError(f"duplicate change_id: {change_id}")
        change_ids.add(change_id)
        change_records.append(
            {
                "change_id": change_id,
                "path": _path(raw.get("path"), "change.path"),
                "owner": require_resource_id(raw.get("owner"), "change.owner"),
            }
        )
    history_records: list[dict[str, Any]] = []
    history_ids: set[str] = set()
    for raw in histories:
        _exact(
            raw,
            "history",
            allowed={"history_id", "fingerprint", "path", "owner", "resolution"},
            required={"history_id", "fingerprint", "path", "owner", "resolution"},
        )
        history_id = require_resource_id(raw.get("history_id"), "history.history_id")
        if history_id in history_ids:
            raise ContractError(f"duplicate history_id: {history_id}")
        history_ids.add(history_id)
        history_records.append(
            {
                "history_id": history_id,
                "fingerprint": require_text(
                    raw.get("fingerprint"), "history.fingerprint", maximum=512
                ),
                "path": _path(raw.get("path"), "history.path"),
                "owner": require_resource_id(raw.get("owner"), "history.owner"),
                "resolution": require_text(
                    raw.get("resolution"), "history.resolution", maximum=2048
                ),
            }
        )
    normalized_hypotheses: list[dict[str, Any]] = []
    hypothesis_ids: set[str] = set()
    for raw in hypotheses:
        _exact(
            raw,
            "hypothesis",
            allowed={
                "hypothesis_id",
                "failure_ids",
                "supporting_evidence_refs",
                "counterevidence_refs",
                "confidence",
            },
            required={
                "hypothesis_id",
                "failure_ids",
                "supporting_evidence_refs",
                "counterevidence_refs",
                "confidence",
            },
        )
        failure_ids = _ids(raw.get("failure_ids"), "hypothesis.failure_ids")
        unknown = sorted(set(failure_ids) - set(failure_by_id))
        if unknown:
            raise ContractError(f"hypothesis references unknown failures: {unknown}")
        hypothesis_id = require_resource_id(
            raw.get("hypothesis_id"), "hypothesis.hypothesis_id"
        )
        if hypothesis_id in hypothesis_ids:
            raise ContractError(f"duplicate hypothesis_id: {hypothesis_id}")
        hypothesis_ids.add(hypothesis_id)
        normalized_hypotheses.append(
            {
                "hypothesis_id": hypothesis_id,
                "failure_ids": failure_ids,
                "supporting_evidence_refs": _ids(
                    raw.get("supporting_evidence_refs"),
                    "hypothesis.supporting_evidence_refs",
                ),
                "counterevidence_refs": _ids(
                    raw.get("counterevidence_refs"),
                    "hypothesis.counterevidence_refs",
                    allow_empty=True,
                ),
                "confidence": _number(
                    raw.get("confidence"), "hypothesis.confidence", maximum=1
                ),
            }
        )
    roots = [
        item for item in failure_by_id.values() if not item["upstream_failure_ids"]
    ]
    suppressed = [
        item["failure_id"]
        for item in failure_by_id.values()
        if item["upstream_failure_ids"]
    ]
    downstream_by_upstream: dict[str, list[str]] = defaultdict(list)
    for failure in failure_by_id.values():
        for upstream_id in failure["upstream_failure_ids"]:
            downstream_by_upstream[upstream_id].append(failure["failure_id"])
    defects: list[dict[str, Any]] = []
    for root in sorted(roots, key=lambda item: item["failure_id"]):
        cascade_ids = {root["failure_id"]}
        cascade_frontier = deque([root["failure_id"]])
        while cascade_frontier:
            current = cascade_frontier.popleft()
            for child in downstream_by_upstream[current]:
                if child not in cascade_ids:
                    cascade_ids.add(child)
                    cascade_frontier.append(child)
        cascade = [failure_by_id[failure_id] for failure_id in sorted(cascade_ids)]
        cascade_paths = {
            repository_path for item in cascade for repository_path in item["changed_paths"]
        }
        cascade_fingerprints = {item["fingerprint"] for item in cascade}
        correlated_changes = [
            item for item in change_records if item["path"] in cascade_paths
        ]
        correlated_history = [
            item
            for item in history_records
            if item["fingerprint"] in cascade_fingerprints
            or item["path"] in cascade_paths
        ]
        owners = sorted(
            {
                value
                for value in (
                    *(item["owner"] for item in cascade),
                    *(item["owner"] for item in correlated_changes),
                    *(item["owner"] for item in correlated_history),
                )
                if value is not None
            }
        )
        defects.append(
            {
                "defect_id": "defect-" + digest_json(
                    {"failure": root["failure_id"], "fingerprint": root["fingerprint"]}
                )[7:27],
                "root_failure_id": root["failure_id"],
                "severity": max(
                    (item["severity"] for item in cascade),
                    key=lambda value: _SEVERITY[value],
                ),
                "owners": owners,
                "change_correlations": correlated_changes,
                "history_correlations": correlated_history,
                "hypotheses": [
                    item
                    for item in normalized_hypotheses
                    if set(item["failure_ids"]).intersection(cascade_ids)
                ],
                "minimal_reproduction": min(
                    (item["reproduction_steps"] for item in cascade),
                    key=lambda value: (len(value), value),
                ),
            }
        )
    return _result(
        "PARTIAL",
        "DEFECT_TRIAGE_PROPOSALS_CREATED",
        {
            "defects": defects,
            "suppressed_cascade_failure_ids": sorted(suppressed),
            "upstream_failures_remain_visible": True,
            "reproduction_execution": "NOT_RUN",
            "ownership_notification": "NOT_RUN",
        },
    )


_FORBIDDEN_REPAIR_KINDS: Final = frozenset(
    {
        "weaken-test",
        "disable-security",
        "broaden-permission",
        "delete-evidence",
        "skip-validation",
    }
)


def plan_advanced_repair(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Select a bounded repair alternative only after evidence thresholds pass."""

    request = _object(inputs, "repair request")
    _exact(
        request,
        "repair request",
        allowed={
            "defect_id",
            "reproduction",
            "root_cause_confidence",
            "confidence_threshold",
            "max_attempts",
            "alternatives",
            "_runtime_context",
        },
        required={
            "defect_id",
            "reproduction",
            "root_cause_confidence",
            "alternatives",
        },
    )
    _validated_runtime_context(request)
    defect_id = require_resource_id(request.get("defect_id"), "defect_id")
    reproduction = _object(request.get("reproduction"), "reproduction")
    _exact(
        reproduction,
        "reproduction",
        allowed={"status", "evidence_digest"},
        required={"status", "evidence_digest"},
    )
    reproduction_status = require_text(
        reproduction.get("status"), "reproduction.status"
    ).upper()
    if reproduction_status not in {"REPRODUCED", "NOT_REPRODUCED", "INCONCLUSIVE"}:
        raise ContractError("reproduction.status is invalid")
    reproduction_digest = _sha256(
        reproduction.get("evidence_digest"), "reproduction.evidence_digest"
    )
    root_confidence = _number(
        request.get("root_cause_confidence"), "root_cause_confidence", maximum=1
    )
    confidence_threshold = _number(
        request.get("confidence_threshold", 0.8), "confidence_threshold", maximum=1
    )
    max_attempts = _integer(
        request.get("max_attempts", 3), "max_attempts", minimum=1, maximum=10
    )
    alternatives = _objects(request.get("alternatives"), "alternatives")
    normalized: list[dict[str, Any]] = []
    alternative_ids: set[str] = set()
    for raw in alternatives:
        _exact(
            raw,
            "repair alternative",
            allowed={
                "alternative_id",
                "changes",
                "validation_steps",
                "rollback_steps",
                "estimated_attempts",
            },
            required={
                "alternative_id",
                "changes",
                "validation_steps",
                "rollback_steps",
                "estimated_attempts",
            },
        )
        alternative_id = require_resource_id(
            raw.get("alternative_id"), "alternative.alternative_id"
        )
        if alternative_id in alternative_ids:
            raise ContractError(f"duplicate repair alternative: {alternative_id}")
        alternative_ids.add(alternative_id)
        changes = _objects(raw.get("changes"), "alternative.changes")
        normalized_changes: list[dict[str, str]] = []
        forbidden: list[str] = []
        for change in changes:
            _exact(
                change,
                "repair change",
                allowed={"path", "kind"},
                required={"path", "kind"},
            )
            kind = require_resource_id(change.get("kind"), "repair change.kind")
            if kind in _FORBIDDEN_REPAIR_KINDS:
                forbidden.append(kind)
            normalized_changes.append(
                {"path": _path(change.get("path"), "repair change.path"), "kind": kind}
            )
        estimated_attempts = _integer(
            raw.get("estimated_attempts"),
            "alternative.estimated_attempts",
            minimum=1,
            maximum=10,
        )
        normalized.append(
            {
                "alternative_id": alternative_id,
                "changes": normalized_changes,
                "validation_steps": _strings(
                    raw.get("validation_steps"), "alternative.validation_steps"
                ),
                "rollback_steps": _strings(
                    raw.get("rollback_steps"), "alternative.rollback_steps"
                ),
                "estimated_attempts": estimated_attempts,
                "forbidden_changes": sorted(set(forbidden)),
                "eligible": not forbidden and estimated_attempts <= max_attempts,
            }
        )
    blockers: list[str] = []
    if reproduction_status != "REPRODUCED":
        blockers.append("REPRODUCTION_REQUIRED")
    if root_confidence < confidence_threshold:
        blockers.append("ROOT_CAUSE_CONFIDENCE_BELOW_THRESHOLD")
    eligible = [item for item in normalized if item["eligible"]]
    if not eligible:
        blockers.append("NO_SAFE_REPAIR_ALTERNATIVE")
    selected = (
        min(eligible, key=lambda item: (item["estimated_attempts"], item["alternative_id"]))
        if eligible and not blockers
        else None
    )
    plan = {
        "defect_id": defect_id,
        "reproduction_evidence_digest": reproduction_digest,
        "root_cause_confidence": root_confidence,
        "confidence_threshold": confidence_threshold,
        "max_attempts": max_attempts,
        "alternatives": normalized,
        "selected_alternative_id": selected["alternative_id"] if selected else None,
        "validation_required": True,
        "rollback_required": True,
    }
    plan["plan_digest"] = digest_json(plan)
    return _result(
        "BLOCKED" if blockers else "SUCCEEDED",
        "REPAIR_THRESHOLDS_NOT_MET" if blockers else "REPAIR_PLAN_CREATED",
        {
            "repair_plan": plan,
            "blockers": blockers,
            "patch_application": "NOT_RUN",
            "validation_execution": "NOT_RUN",
            "rollback_execution": "NOT_RUN",
            "merge_authorized": False,
        },
    )


_GRAPH_NODE_KINDS: Final = frozenset(
    {"SOURCE", "MODULE", "API", "DATA", "CONFIG", "TEST", "ARTIFACT"}
)
_GRAPH_EDGE_KINDS: Final = frozenset(
    {"DEPENDS_ON", "CALLS", "COVERS", "GENERATES", "CONFIGURES", "USES"}
)


def analyze_typed_impact(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Propagate changes through an explicit typed graph, but never trust it."""

    request = _object(inputs, "impact request")
    _exact(
        request,
        "impact request",
        allowed={
            "graph",
            "changed_node_ids",
            "all_test_ids",
            "trusted_graph_receipt",
            "_runtime_context",
        },
        required={"graph", "changed_node_ids", "all_test_ids"},
    )
    _validated_runtime_context(request)
    graph = _object(request.get("graph"), "graph")
    _exact(
        graph,
        "graph",
        allowed={"graph_id", "nodes", "edges", "graph_digest"},
        required={"graph_id", "nodes", "edges", "graph_digest"},
    )
    graph_id = require_resource_id(graph.get("graph_id"), "graph.graph_id")
    nodes = _objects(graph.get("nodes"), "graph.nodes")
    node_by_id: dict[str, str] = {}
    for raw in nodes:
        _exact(
            raw,
            "graph node",
            allowed={"node_id", "kind"},
            required={"node_id", "kind"},
        )
        node_id = require_resource_id(raw.get("node_id"), "graph.node_id")
        if node_id in node_by_id:
            raise ContractError(f"duplicate graph node: {node_id}")
        kind = require_text(raw.get("kind"), "graph.node.kind").upper()
        if kind not in _GRAPH_NODE_KINDS:
            raise ContractError(f"unsupported graph node kind: {kind}")
        node_by_id[node_id] = kind
    edges = _objects(graph.get("edges", []), "graph.edges", allow_empty=True)
    normalized_edges: list[dict[str, str]] = []
    propagation: dict[str, list[str]] = defaultdict(list)
    edge_keys: set[tuple[str, str, str, str]] = set()
    for raw in edges:
        _exact(
            raw,
            "graph edge",
            allowed={"source", "target", "kind", "direction"},
            required={"source", "target", "kind", "direction"},
        )
        source = require_resource_id(raw.get("source"), "graph.edge.source")
        target = require_resource_id(raw.get("target"), "graph.edge.target")
        if source not in node_by_id or target not in node_by_id or source == target:
            raise ContractError("graph edge must bind two distinct declared nodes")
        kind = require_text(raw.get("kind"), "graph.edge.kind").upper()
        if kind not in _GRAPH_EDGE_KINDS:
            raise ContractError(f"unsupported graph edge kind: {kind}")
        direction = require_text(raw.get("direction"), "graph.edge.direction")
        if direction not in {"source-to-target", "target-to-source", "bidirectional"}:
            raise ContractError("graph edge direction is invalid")
        key = source, target, kind, direction
        if key in edge_keys:
            raise ContractError("duplicate graph edge")
        edge_keys.add(key)
        normalized_edges.append(
            {"source": source, "target": target, "kind": kind, "direction": direction}
        )
        if direction in {"source-to-target", "bidirectional"}:
            propagation[source].append(target)
        if direction in {"target-to-source", "bidirectional"}:
            propagation[target].append(source)
    canonical_graph = {
        "graph_id": graph_id,
        "nodes": [
            {"node_id": node_id, "kind": node_by_id[node_id]}
            for node_id in sorted(node_by_id)
        ],
        "edges": sorted(
            normalized_edges,
            key=lambda item: (
                item["source"], item["target"], item["kind"], item["direction"]
            ),
        ),
    }
    supplied_digest = _sha256(graph.get("graph_digest"), "graph.graph_digest")
    canonical_digest = digest_json(canonical_graph)[7:]
    if supplied_digest != canonical_digest:
        raise ContractError("graph.graph_digest does not match canonical typed graph")
    changed = _ids(request.get("changed_node_ids"), "changed_node_ids")
    unknown_changed = sorted(set(changed) - set(node_by_id))
    if unknown_changed:
        raise ContractError(f"changed nodes are absent from graph: {unknown_changed}")
    all_tests = _ids(request.get("all_test_ids"), "all_test_ids")
    graph_tests = {node_id for node_id, kind in node_by_id.items() if kind == "TEST"}
    if not set(all_tests).issubset(graph_tests):
        raise ContractError("all_test_ids must identify TEST nodes in the graph")
    visited = set(changed)
    frontier = deque(sorted(changed))
    propagation_paths: list[dict[str, str]] = []
    while frontier:
        current = frontier.popleft()
        for impacted in sorted(propagation[current]):
            propagation_paths.append({"from": current, "to": impacted})
            if impacted not in visited:
                visited.add(impacted)
                frontier.append(impacted)
    candidate_tests = sorted(visited.intersection(all_tests))
    receipt_fields = sorted(
        _object(request.get("trusted_graph_receipt", {}), "trusted_graph_receipt")
    )
    outputs = {
        "graph_id": graph_id,
        "graph_digest": supplied_digest,
        "candidate_impacted_tests": candidate_tests,
        "propagation_paths": propagation_paths,
        "selected_test_scope": sorted(all_tests),
        "scope": "FULL_REQUIRED",
        "full_regression_required": True,
        "caller_graph_receipt_fields_observed": receipt_fields,
        "caller_graph_receipt_accepted": False,
        "trusted_graph_receipt": "NOT_RUN",
    }
    outputs["report_digest"] = digest_json(outputs)
    return _result(
        "BLOCKED",
        "TRUSTED_GRAPH_RECEIPT_REQUIRED",
        outputs,
    )


_GENERATOR_STRATEGIES: Final = frozenset(
    {"boundary", "equivalence", "random", "stateful", "grammar", "combinatorial"}
)
_MUTATION_KINDS: Final = frozenset(
    {
        "conditional-boundary",
        "arithmetic-operator",
        "return-value",
        "exception-removal",
        "authorization-bypass",
        "transaction-boundary",
    }
)


def plan_advanced_testing(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Bind invariant, property, fuzz, corpus, mutation, and survivor plans."""

    request = _object(inputs, "advanced testing request")
    _exact(
        request,
        "advanced testing request",
        allowed={
            "invariants",
            "generators",
            "shrinkers",
            "properties",
            "fuzz_targets",
            "corpus",
            "mutation_operators",
            "survivors",
            "_runtime_context",
        },
        required={
            "invariants",
            "generators",
            "shrinkers",
            "properties",
            "fuzz_targets",
            "corpus",
            "mutation_operators",
        },
    )
    _validated_runtime_context(request)
    invariants = _objects(request.get("invariants"), "invariants")
    generators = _objects(request.get("generators"), "generators")
    shrinkers = _objects(request.get("shrinkers"), "shrinkers")
    properties = _objects(request.get("properties"), "properties")
    fuzz_targets = _objects(request.get("fuzz_targets"), "fuzz_targets")
    corpus = _objects(request.get("corpus"), "corpus")
    operators = _objects(request.get("mutation_operators"), "mutation_operators")
    survivors = _objects(
        request.get("survivors", []), "survivors", allow_empty=True
    )
    invariant_by_id: dict[str, dict[str, Any]] = {}
    for raw in invariants:
        _exact(
            raw,
            "invariant",
            allowed={"invariant_id", "statement", "oracle_ref"},
            required={"invariant_id", "statement", "oracle_ref"},
        )
        invariant_id = require_resource_id(
            raw.get("invariant_id"), "invariant.invariant_id"
        )
        if invariant_id in invariant_by_id:
            raise ContractError(f"duplicate invariant: {invariant_id}")
        invariant_by_id[invariant_id] = {
            "invariant_id": invariant_id,
            "statement": require_text(
                raw.get("statement"), "invariant.statement", maximum=8192
            ),
            "oracle_ref": require_resource_id(
                raw.get("oracle_ref"), "invariant.oracle_ref"
            ),
        }
    generator_by_id: dict[str, dict[str, Any]] = {}
    for raw in generators:
        _exact(
            raw,
            "generator",
            allowed={"generator_id", "strategy", "domain"},
            required={"generator_id", "strategy", "domain"},
        )
        generator_id = require_resource_id(
            raw.get("generator_id"), "generator.generator_id"
        )
        if generator_id in generator_by_id:
            raise ContractError(f"duplicate generator: {generator_id}")
        strategy = require_text(raw.get("strategy"), "generator.strategy")
        if strategy not in _GENERATOR_STRATEGIES:
            raise ContractError(f"unsupported generator strategy: {strategy}")
        domain = _object(raw.get("domain"), "generator.domain")
        generator_by_id[generator_id] = {
            "generator_id": generator_id,
            "strategy": strategy,
            "domain": strict_json(domain, "generator.domain"),
        }
    shrinker_by_id: dict[str, dict[str, Any]] = {}
    for raw in shrinkers:
        _exact(
            raw,
            "shrinker",
            allowed={"shrinker_id", "strategy", "preserves_invariant_refs"},
            required={"shrinker_id", "strategy", "preserves_invariant_refs"},
        )
        shrinker_id = require_resource_id(raw.get("shrinker_id"), "shrinker.shrinker_id")
        if shrinker_id in shrinker_by_id:
            raise ContractError(f"duplicate shrinker: {shrinker_id}")
        preserved = _ids(
            raw.get("preserves_invariant_refs"), "shrinker.preserves_invariant_refs"
        )
        if not set(preserved).issubset(invariant_by_id):
            raise ContractError("shrinker references an unknown invariant")
        shrinker_by_id[shrinker_id] = {
            "shrinker_id": shrinker_id,
            "strategy": require_resource_id(raw.get("strategy"), "shrinker.strategy"),
            "preserves_invariant_refs": preserved,
        }
    property_plans: list[dict[str, Any]] = []
    property_ids: set[str] = set()
    for raw in properties:
        _exact(
            raw,
            "property",
            allowed={"property_id", "invariant_refs", "generator_id", "shrinker_id"},
            required={"property_id", "invariant_refs", "generator_id", "shrinker_id"},
        )
        property_id = require_resource_id(raw.get("property_id"), "property.property_id")
        if property_id in property_ids:
            raise ContractError(f"duplicate property: {property_id}")
        property_ids.add(property_id)
        invariant_refs = _ids(raw.get("invariant_refs"), "property.invariant_refs")
        generator_id = require_resource_id(raw.get("generator_id"), "property.generator_id")
        shrinker_id = require_resource_id(raw.get("shrinker_id"), "property.shrinker_id")
        if (
            not set(invariant_refs).issubset(invariant_by_id)
            or generator_id not in generator_by_id
            or shrinker_id not in shrinker_by_id
        ):
            raise ContractError(f"property {property_id} has an unknown reference")
        property_plans.append(
            {
                "property_id": property_id,
                "invariant_refs": invariant_refs,
                "generator": generator_by_id[generator_id],
                "shrinker": shrinker_by_id[shrinker_id],
            }
        )
    fuzz_by_id: dict[str, dict[str, Any]] = {}
    for raw in fuzz_targets:
        _exact(
            raw,
            "fuzz target",
            allowed={"target_id", "path", "entrypoint", "invariant_refs"},
            required={"target_id", "path", "entrypoint", "invariant_refs"},
        )
        target_id = require_resource_id(raw.get("target_id"), "fuzz target.target_id")
        if target_id in fuzz_by_id:
            raise ContractError(f"duplicate fuzz target: {target_id}")
        invariant_refs = _ids(raw.get("invariant_refs"), "fuzz target.invariant_refs")
        if not set(invariant_refs).issubset(invariant_by_id):
            raise ContractError("fuzz target references an unknown invariant")
        fuzz_by_id[target_id] = {
            "target_id": target_id,
            "path": _path(raw.get("path"), "fuzz target.path"),
            "entrypoint": require_resource_id(
                raw.get("entrypoint"), "fuzz target.entrypoint"
            ),
            "invariant_refs": invariant_refs,
        }
    corpus_records: list[dict[str, str]] = []
    corpus_ids: set[str] = set()
    for raw in corpus:
        _exact(
            raw,
            "corpus entry",
            allowed={"corpus_id", "target_id", "sha256", "role"},
            required={"corpus_id", "target_id", "sha256", "role"},
        )
        corpus_id = require_resource_id(raw.get("corpus_id"), "corpus.corpus_id")
        if corpus_id in corpus_ids:
            raise ContractError(f"duplicate corpus entry: {corpus_id}")
        corpus_ids.add(corpus_id)
        target_id = require_resource_id(raw.get("target_id"), "corpus.target_id")
        if target_id not in fuzz_by_id:
            raise ContractError("corpus entry references an unknown fuzz target")
        role = require_text(raw.get("role"), "corpus.role")
        if role not in {"development", "negative", "holdout", "regression"}:
            raise ContractError("corpus.role is invalid")
        corpus_records.append(
            {
                "corpus_id": corpus_id,
                "target_id": target_id,
                "sha256": _sha256(raw.get("sha256"), "corpus.sha256"),
                "role": role,
            }
        )
    operator_by_id: dict[str, dict[str, str]] = {}
    for raw in operators:
        _exact(
            raw,
            "mutation operator",
            allowed={"operator_id", "kind", "target_id"},
            required={"operator_id", "kind", "target_id"},
        )
        operator_id = require_resource_id(
            raw.get("operator_id"), "mutation operator.operator_id"
        )
        kind = require_text(raw.get("kind"), "mutation operator.kind")
        target_id = require_resource_id(
            raw.get("target_id"), "mutation operator.target_id"
        )
        if operator_id in operator_by_id or kind not in _MUTATION_KINDS:
            raise ContractError("mutation operator is duplicate or unsupported")
        if target_id not in fuzz_by_id:
            raise ContractError("mutation operator references an unknown target")
        operator_by_id[operator_id] = {
            "operator_id": operator_id,
            "kind": kind,
            "target_id": target_id,
        }
    survivor_regressions: list[dict[str, str]] = []
    survivor_ids: set[str] = set()
    for raw in survivors:
        _exact(
            raw,
            "survivor",
            allowed={"survivor_id", "operator_id", "counterexample_digest"},
            required={"survivor_id", "operator_id", "counterexample_digest"},
        )
        survivor_id = require_resource_id(raw.get("survivor_id"), "survivor.survivor_id")
        if survivor_id in survivor_ids:
            raise ContractError(f"duplicate survivor: {survivor_id}")
        survivor_ids.add(survivor_id)
        operator_id = require_resource_id(raw.get("operator_id"), "survivor.operator_id")
        if operator_id not in operator_by_id:
            raise ContractError("survivor references an unknown mutation operator")
        survivor_regressions.append(
            {
                "survivor_id": survivor_id,
                "operator_id": operator_id,
                "counterexample_digest": _sha256(
                    raw.get("counterexample_digest"), "survivor.counterexample_digest"
                ),
                "regression_test_id": "regression-"
                + digest_json({"survivor": survivor_id, "operator": operator_id})[7:27],
            }
        )
    plan = {
        "invariants": list(invariant_by_id.values()),
        "property_plans": property_plans,
        "fuzz_targets": list(fuzz_by_id.values()),
        "corpus": corpus_records,
        "mutation_operators": list(operator_by_id.values()),
        "survivor_regressions": survivor_regressions,
    }
    plan["plan_digest"] = digest_json(plan)
    return _result(
        "PARTIAL",
        "ADVANCED_TESTING_PLAN_CREATED",
        {
            "advanced_testing_plan": plan,
            "property_execution": "NOT_RUN",
            "shrinking_execution": "NOT_RUN",
            "fuzz_execution": "NOT_RUN",
            "mutation_execution": "NOT_RUN",
            "survivor_regression_materialization": "NOT_RUN",
        },
        implementation_state="EXTERNAL_ADAPTER_REQUIRED",
    )


def build_structured_report(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create JSON, JUnit, and HTML export models without writing files."""

    request = _object(inputs, "report request")
    _exact(
        request,
        "report request",
        allowed={
            "requirements",
            "test_results",
            "defects",
            "patches",
            "evidence",
            "_runtime_context",
        },
        required={"test_results"},
    )
    _validated_runtime_context(request)
    requirements = _objects(
        request.get("requirements", []), "requirements", allow_empty=True
    )
    tests = _objects(request.get("test_results"), "test_results")
    defects = _objects(request.get("defects", []), "defects", allow_empty=True)
    patches = _objects(request.get("patches", []), "patches", allow_empty=True)
    evidence = _objects(request.get("evidence", []), "evidence", allow_empty=True)
    requirement_summary: Counter[str] = Counter()
    requirement_ids: set[str] = set()
    for raw in requirements:
        _exact(
            raw,
            "report requirement",
            allowed={"requirement_id", "priority", "status"},
            required={"requirement_id", "priority", "status"},
        )
        requirement_id = require_resource_id(
            raw.get("requirement_id"), "requirement.requirement_id"
        )
        if requirement_id in requirement_ids:
            raise ContractError(f"duplicate report requirement: {requirement_id}")
        requirement_ids.add(requirement_id)
        priority = require_text(raw.get("priority"), "requirement.priority")
        status = require_text(raw.get("status"), "requirement.status").upper()
        if priority not in _PRIORITY or status not in {
            "COVERED",
            "PARTIAL",
            "UNCOVERED",
            "BLOCKED",
        }:
            raise ContractError("report requirement fields are invalid")
        requirement_summary[f"{priority}:{status}"] += 1
    test_summary: Counter[str] = Counter()
    normalized_tests: list[dict[str, str]] = []
    test_ids: set[str] = set()
    for raw in tests:
        _exact(
            raw,
            "report test",
            allowed={"test_case_id", "test_type", "status"},
            required={"test_case_id", "test_type", "status"},
        )
        test_id = require_resource_id(raw.get("test_case_id"), "test.test_case_id")
        if test_id in test_ids:
            raise ContractError(f"duplicate report test: {test_id}")
        test_ids.add(test_id)
        test_type = require_resource_id(raw.get("test_type"), "test.test_type")
        status = require_text(raw.get("status"), "test.status").upper()
        if status not in {*_TERMINAL, "NOT_RUN", "SKIPPED", "UNKNOWN"}:
            raise ContractError("report test status is invalid")
        test_summary[f"{test_type}:{status}"] += 1
        normalized_tests.append(
            {"test_case_id": test_id, "test_type": test_type, "status": status}
        )
    defect_summary: Counter[str] = Counter()
    defect_ids: set[str] = set()
    for raw in defects:
        _exact(
            raw,
            "report defect",
            allowed={"defect_id", "severity", "status"},
            required={"defect_id", "severity", "status"},
        )
        defect_id = require_resource_id(raw.get("defect_id"), "defect.defect_id")
        if defect_id in defect_ids:
            raise ContractError(f"duplicate report defect: {defect_id}")
        defect_ids.add(defect_id)
        severity = require_text(raw.get("severity"), "defect.severity").upper()
        status = require_text(raw.get("status"), "defect.status").upper()
        if severity not in _SEVERITY or status not in {
            "OPEN",
            "TRIAGED",
            "REPAIRED",
            "VERIFIED",
            "BLOCKED",
        }:
            raise ContractError("report defect fields are invalid")
        defect_summary[f"{severity}:{status}"] += 1
    patch_summary: Counter[str] = Counter()
    patch_ids: set[str] = set()
    for raw in patches:
        _exact(
            raw,
            "report patch",
            allowed={"patch_id", "status", "risk"},
            required={"patch_id", "status", "risk"},
        )
        patch_id = require_resource_id(raw.get("patch_id"), "patch.patch_id")
        if patch_id in patch_ids:
            raise ContractError(f"duplicate report patch: {patch_id}")
        patch_ids.add(patch_id)
        status = require_text(raw.get("status"), "patch.status").upper()
        risk = require_text(raw.get("risk"), "patch.risk").upper()
        if risk not in _SEVERITY or status not in {
            "PROPOSED",
            "VALIDATED",
            "REJECTED",
            "ROLLED_BACK",
            "NOT_RUN",
        }:
            raise ContractError("report patch fields are invalid")
        patch_summary[f"{risk}:{status}"] += 1
    evidence_summary: Counter[str] = Counter()
    evidence_ids: set[str] = set()
    for raw in evidence:
        _exact(
            raw,
            "report evidence",
            allowed={"evidence_id", "state", "sha256"},
            required={"evidence_id", "state", "sha256"},
        )
        evidence_id = require_resource_id(raw.get("evidence_id"), "evidence.evidence_id")
        if evidence_id in evidence_ids:
            raise ContractError(f"duplicate report evidence: {evidence_id}")
        evidence_ids.add(evidence_id)
        state = require_text(raw.get("state"), "evidence.state").upper()
        if state not in {
            "VERIFIED_LOCAL",
            "INVALID",
            "QUARANTINED",
            "NOT_RUN",
            "UNKNOWN",
        }:
            raise ContractError("report evidence state is invalid")
        _sha256(raw.get("sha256"), "evidence.sha256")
        evidence_summary[state] += 1
    summaries = {
        "requirements": dict(sorted(requirement_summary.items())),
        "tests": dict(sorted(test_summary.items())),
        "defects": dict(sorted(defect_summary.items())),
        "patches": dict(sorted(patch_summary.items())),
        "evidence": dict(sorted(evidence_summary.items())),
    }
    json_document = {"schema_version": "1.0", "summaries": summaries}
    junit_model = {
        "suite_name": "autonomous-qa",
        "tests": len(normalized_tests),
        "failures": sum(item["status"] == "FAILED" for item in normalized_tests),
        "skipped": sum(
            item["status"] in {"SKIPPED", "NOT_RUN", "UNKNOWN"}
            for item in normalized_tests
        ),
        "cases": normalized_tests,
    }
    html_model = {
        "title": "Autonomous QA Report",
        "sections": [
            {"section_id": name, "summary": value}
            for name, value in summaries.items()
        ],
        "scripts_allowed": False,
        "external_resources_allowed": False,
    }
    exports = {
        "json": {
            "media_type": "application/json",
            "model": json_document,
            "digest": digest_json(json_document),
        },
        "junit": {
            "media_type": "application/junit+xml",
            "model": junit_model,
            "digest": digest_json(junit_model),
        },
        "html": {
            "media_type": "text/html",
            "model": html_model,
            "digest": digest_json(html_model),
        },
    }
    incomplete = any(
        item["status"] in {"FAILED", "BLOCKED", "NOT_RUN", "SKIPPED", "UNKNOWN"}
        for item in normalized_tests
    )
    return _result(
        "PARTIAL" if incomplete else "SUCCEEDED",
        "REPORT_CREATED_WITH_VISIBLE_GAPS" if incomplete else "REPORT_MODELS_CREATED",
        {
            "summaries": summaries,
            "export_plans": exports,
            "files_written": False,
            "publication": "NOT_RUN",
            "signature": "NOT_RUN",
            "certified": False,
        },
    )


def create_durable_store_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Plan checkpoint/restore/rebuild operations behind a trusted store binder."""

    request = _object(inputs, "durable store request")
    _exact(
        request,
        "durable store request",
        allowed={
            "operation",
            "run_id",
            "sequence",
            "expected_version",
            "lease",
            "fence_token",
            "state",
            "events",
            "trusted_store_binder",
            "_runtime_context",
        },
        required={
            "operation",
            "run_id",
            "sequence",
            "expected_version",
            "lease",
            "fence_token",
        },
    )
    runtime_context = _validated_runtime_context(request)
    operation = require_text(request.get("operation"), "operation")
    if operation not in {"checkpoint", "restore", "rebuild"}:
        raise ContractError("durable store operation is invalid")
    run_id = require_resource_id(request.get("run_id"), "run_id")
    sequence = _integer(request.get("sequence"), "sequence", maximum=10_000_000)
    expected_version = _integer(
        request.get("expected_version"), "expected_version", maximum=10_000_000
    )
    lease = _object(request.get("lease"), "lease")
    _exact(
        lease,
        "lease",
        allowed={"owner", "epoch", "expires_at"},
        required={"owner", "epoch", "expires_at"},
    )
    normalized_lease = {
        "owner": require_resource_id(lease.get("owner"), "lease.owner"),
        "epoch": _integer(lease.get("epoch"), "lease.epoch", minimum=1),
        "expires_at": require_text(lease.get("expires_at"), "lease.expires_at", maximum=64),
    }
    _timestamp(normalized_lease["expires_at"], "lease.expires_at")
    fence_token = _integer(
        request.get("fence_token"), "fence_token", minimum=1, maximum=10_000_000
    )
    state = strict_json(request.get("state", {}), "durable store state")
    events = _objects(request.get("events", []), "events", allow_empty=True)
    normalized_events: list[dict[str, Any]] = []
    previous = 0
    prior_digest = "0" * 64
    for raw in events:
        _exact(
            raw,
            "rebuild event",
            allowed={"sequence", "kind", "payload", "previous_digest", "event_digest"},
            required={"sequence", "kind", "payload", "previous_digest", "event_digest"},
        )
        event_sequence = _integer(
            raw.get("sequence"), "event.sequence", minimum=1, maximum=10_000_000
        )
        if event_sequence != previous + 1:
            raise ContractError("rebuild events must form a contiguous sequence")
        previous = event_sequence
        event_kind = require_resource_id(raw.get("kind"), "event.kind")
        event_payload = strict_json(raw.get("payload"), "event.payload")
        previous_digest = _sha256(
            raw.get("previous_digest"), "event.previous_digest"
        )
        event_digest = _sha256(raw.get("event_digest"), "event.event_digest")
        if previous_digest != prior_digest:
            raise ContractError("rebuild event digest chain is not contiguous")
        expected_event_digest = digest_json(
            {
                "sequence": event_sequence,
                "kind": event_kind,
                "payload": event_payload,
                "previous_digest": previous_digest,
            }
        )[7:]
        if event_digest != expected_event_digest:
            raise ContractError("rebuild event digest does not match canonical event content")
        prior_digest = event_digest
        normalized_events.append(
            {
                "sequence": event_sequence,
                "kind": event_kind,
                "payload": event_payload,
                "previous_digest": previous_digest,
                "event_digest": event_digest,
            }
        )
    if operation == "rebuild" and not normalized_events:
        raise ContractError("rebuild requires a non-empty event sequence")
    if operation == "rebuild" and normalized_events[-1]["sequence"] != sequence:
        raise ContractError("rebuild event tail must match the requested sequence")
    contract = {
        "operation": operation,
        "run_id": run_id,
        "runtime_scope": {
            "tenant_id": runtime_context.get("tenant_id"),
            "project_id": runtime_context.get("project_id"),
        },
        "sequence": sequence,
        "state": state,
        "compare_and_swap": {
            "expected_version": expected_version,
            "next_version": expected_version + 1,
            "mismatch_outcome": "BLOCKED",
        },
        "lease": normalized_lease,
        "fence": {
            "token": fence_token,
            "stale_token_rejected": True,
            "epoch_bound": True,
        },
        "event_rebuild": {
            "events": normalized_events,
            "chain_revalidation_required": True,
            "tail_truncation_rejected": True,
        },
        "restore": {
            "snapshot_digest_required": True,
            "replay_after_snapshot_required": True,
            "post_restore_verification_required": True,
        },
    }
    contract["operation_digest"] = digest_json(contract)
    receipt_fields = sorted(
        _object(request.get("trusted_store_binder", {}), "trusted_store_binder")
    )
    return _result(
        "BLOCKED",
        "TRUSTED_DURABLE_STORE_BINDER_REQUIRED",
        {
            "operation_contract": contract,
            "persisted": False,
            "restored": False,
            "event_rebuild_executed": False,
            "caller_store_binder_fields_observed": receipt_fields,
            "caller_store_binder_accepted": False,
            "durable_store_adapter": "NOT_RUN",
        },
        implementation_state="EXTERNAL_ADAPTER_REQUIRED",
    )


def estimate_runtime_cost(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Estimate DAG runtime and cost from explicit, timestamped assumptions."""

    request = _object(inputs, "runtime estimate request")
    _exact(
        request,
        "runtime estimate request",
        allowed={
            "tasks",
            "parallelism",
            "queue_seconds",
            "retry_probability",
            "retry_seconds",
            "repair_seconds",
            "regression_seconds",
            "publish_seconds",
            "pricing",
            "calibration",
            "_runtime_context",
        },
        required={"tasks", "pricing"},
    )
    _validated_runtime_context(request)
    tasks = _objects(request.get("tasks"), "tasks")
    parallelism = _integer(
        request.get("parallelism", 1), "parallelism", minimum=1, maximum=1024
    )
    task_by_id: dict[str, dict[str, Any]] = {}
    dependencies: dict[str, list[str]] = {}
    for raw in tasks:
        _exact(
            raw,
            "estimate task",
            allowed={
                "task_id",
                "phase",
                "dependency_ids",
                "estimated_seconds",
                "resource_units",
            },
            required={
                "task_id",
                "phase",
                "dependency_ids",
                "estimated_seconds",
                "resource_units",
            },
        )
        task_id = require_resource_id(raw.get("task_id"), "task.task_id")
        if task_id in task_by_id:
            raise ContractError(f"duplicate estimate task: {task_id}")
        task_by_id[task_id] = {
            "task_id": task_id,
            "phase": require_resource_id(raw.get("phase"), "task.phase"),
            "dependency_ids": _ids(raw.get("dependency_ids"), "task.dependency_ids", allow_empty=True),
            "estimated_seconds": _number(
                raw.get("estimated_seconds"), "task.estimated_seconds", maximum=31_536_000
            ),
            "resource_units": _number(
                raw.get("resource_units"), "task.resource_units", maximum=1_000_000
            ),
        }
        dependencies[task_id] = task_by_id[task_id]["dependency_ids"]
    ordered = _topological_order(list(task_by_id), dependencies, "estimate DAG")
    finish: dict[str, float] = {}
    predecessor: dict[str, str | None] = {}
    for task_id in ordered:
        dependency = max(
            dependencies[task_id], key=lambda value: finish[value], default=None
        )
        predecessor[task_id] = dependency
        finish[task_id] = task_by_id[task_id]["estimated_seconds"] + (
            finish[dependency] if dependency is not None else 0.0
        )
    terminal = max(ordered, key=lambda value: finish[value])
    critical_path: list[str] = []
    cursor: str | None = terminal
    while cursor is not None:
        critical_path.append(cursor)
        cursor = predecessor[cursor]
    critical_path.reverse()
    phase_seconds: Counter[str] = Counter()
    total_task_seconds = 0.0
    resource_seconds = 0.0
    for task in task_by_id.values():
        phase_seconds[task["phase"]] += task["estimated_seconds"]
        total_task_seconds += task["estimated_seconds"]
        resource_seconds += task["estimated_seconds"] * task["resource_units"]
    queue_seconds = _number(request.get("queue_seconds", 0), "queue_seconds")
    retry_probability = _number(
        request.get("retry_probability", 0), "retry_probability", maximum=1
    )
    retry_seconds = _number(request.get("retry_seconds", 0), "retry_seconds")
    repair_seconds = _number(request.get("repair_seconds", 0), "repair_seconds")
    regression_seconds = _number(
        request.get("regression_seconds", 0), "regression_seconds"
    )
    publish_seconds = _number(request.get("publish_seconds", 0), "publish_seconds")
    parallel_floor = total_task_seconds / parallelism
    expected_runtime = (
        max(finish[terminal], parallel_floor)
        + queue_seconds
        + retry_probability * retry_seconds
        + repair_seconds
        + regression_seconds
        + publish_seconds
    )
    pricing = _object(request.get("pricing"), "pricing")
    _exact(
        pricing,
        "pricing",
        allowed={"currency", "observed_at", "unit_price_per_resource_second"},
        required={"currency", "observed_at", "unit_price_per_resource_second"},
    )
    currency = require_resource_id(pricing.get("currency"), "pricing.currency").upper()
    observed_at = require_text(pricing.get("observed_at"), "pricing.observed_at", maximum=64)
    _timestamp(observed_at, "pricing.observed_at")
    unit_price = _number(
        pricing.get("unit_price_per_resource_second"),
        "pricing.unit_price_per_resource_second",
        maximum=1_000_000,
    )
    average_resource_units = (
        resource_seconds / total_task_seconds if total_task_seconds else 0.0
    )
    billed_resource_seconds = resource_seconds + average_resource_units * (
        retry_probability * retry_seconds
        + repair_seconds
        + regression_seconds
        + publish_seconds
    )
    expected_cost = billed_resource_seconds * unit_price
    history = _objects(request.get("calibration", []), "calibration", allow_empty=True)
    errors: list[float] = []
    for raw in history:
        _exact(
            raw,
            "calibration sample",
            allowed={"predicted_seconds", "actual_seconds"},
            required={"predicted_seconds", "actual_seconds"},
        )
        predicted = _number(
            raw.get("predicted_seconds"), "calibration.predicted_seconds"
        )
        actual = _number(
            raw.get("actual_seconds"), "calibration.actual_seconds", minimum=1e-12
        )
        errors.append(abs(predicted - actual) / actual)
    calibration = {
        "sample_count": len(errors),
        "mean_absolute_percentage_error": sum(errors) / len(errors) if errors else None,
        "status": "CALIBRATED" if len(errors) >= 3 else "INSUFFICIENT_HISTORY",
    }
    estimate = {
        "dag": {
            "task_order": ordered,
            "critical_path": critical_path,
            "critical_path_seconds": finish[terminal],
            "parallel_floor_seconds": parallel_floor,
        },
        "phase_distribution_seconds": dict(sorted(phase_seconds.items())),
        "components": {
            "queue_seconds": queue_seconds,
            "expected_retry_seconds": retry_probability * retry_seconds,
            "repair_seconds": repair_seconds,
            "regression_seconds": regression_seconds,
            "publish_seconds": publish_seconds,
        },
        "expected_runtime_seconds": expected_runtime,
        "pricing": {
            "currency": currency,
            "observed_at": observed_at,
            "unit_price_per_resource_second": unit_price,
        },
        "expected_cost": expected_cost,
        "billed_resource_seconds": billed_resource_seconds,
        "calibration": calibration,
    }
    estimate["estimate_digest"] = digest_json(estimate)
    return _result(
        "PARTIAL",
        "RUNTIME_COST_ESTIMATE_CREATED",
        {
            "estimate": estimate,
            "runtime_execution": "NOT_RUN",
            "caller_price_assertion_accepted": False,
            "trusted_price_receipt": "NOT_RUN",
            "cost_is_estimate_only": True,
            "human_equivalent_time_inferred": False,
        },
    )


def propose_knowledge_update(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create a versioned, reversible KB proposal without enabling it."""

    request = _object(inputs, "knowledge request")
    _exact(
        request,
        "knowledge request",
        allowed={
            "scope",
            "version",
            "sources",
            "rules",
            "metrics",
            "rollback",
            "history",
            "trusted_external_source_receipt",
            "_runtime_context",
        },
        required={"scope", "version", "sources", "rules", "metrics", "rollback"},
    )
    runtime_context = _validated_runtime_context(request)
    scope = _object(request.get("scope"), "scope")
    _exact(
        scope,
        "scope",
        allowed={"tenant_id", "project_id", "audience"},
        required={"tenant_id", "project_id", "audience"},
    )
    normalized_scope = {
        "tenant_id": require_resource_id(scope.get("tenant_id"), "scope.tenant_id"),
        "project_id": require_resource_id(scope.get("project_id"), "scope.project_id"),
        "audience": require_resource_id(scope.get("audience"), "scope.audience"),
    }
    if runtime_context:
        if normalized_scope["tenant_id"] != runtime_context.get("tenant_id"):
            raise ContractError("scope.tenant_id differs from the trusted runtime context")
        if normalized_scope["project_id"] != runtime_context.get("project_id"):
            raise ContractError("scope.project_id differs from the trusted runtime context")
    version = require_resource_id(request.get("version"), "version")
    sources = _objects(request.get("sources"), "sources")
    normalized_sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    external_sources: list[str] = []
    for raw in sources:
        _exact(
            raw,
            "knowledge source",
            allowed={"source_id", "sha256", "state", "confidence", "external"},
            required={"source_id", "sha256", "state", "confidence", "external"},
        )
        source_id = require_resource_id(raw.get("source_id"), "source.source_id")
        if source_id in source_ids:
            raise ContractError(f"duplicate knowledge source: {source_id}")
        source_ids.add(source_id)
        external = _boolean(raw.get("external"), "source.external")
        if external:
            external_sources.append(source_id)
        normalized_sources.append(
            {
                "source_id": source_id,
                "sha256": _sha256(raw.get("sha256"), "source.sha256"),
                "state": require_resource_id(raw.get("state"), "source.state"),
                "confidence": _number(
                    raw.get("confidence"), "source.confidence", maximum=1
                ),
                "external": external,
            }
        )
    rules = _objects(request.get("rules"), "rules")
    normalized_rules: list[dict[str, str]] = []
    rule_ids: set[str] = set()
    for raw in rules:
        _exact(
            raw,
            "knowledge rule",
            allowed={"rule_id", "condition", "recommendation"},
            required={"rule_id", "condition", "recommendation"},
        )
        rule_id = require_resource_id(raw.get("rule_id"), "rule.rule_id")
        if rule_id in rule_ids:
            raise ContractError(f"duplicate knowledge rule: {rule_id}")
        rule_ids.add(rule_id)
        normalized_rules.append(
            {
                "rule_id": rule_id,
                "condition": require_text(
                    raw.get("condition"), "rule.condition", maximum=4096
                ),
                "recommendation": require_text(
                    raw.get("recommendation"), "rule.recommendation", maximum=4096
                ),
            }
        )
    metrics = _objects(request.get("metrics"), "metrics")
    normalized_metrics: list[dict[str, Any]] = []
    for raw in metrics:
        _exact(
            raw,
            "knowledge metric",
            allowed={"name", "baseline", "target", "direction"},
            required={"name", "baseline", "target", "direction"},
        )
        direction = require_text(raw.get("direction"), "metric.direction")
        if direction not in {"increase", "decrease", "maintain"}:
            raise ContractError("metric.direction is invalid")
        normalized_metrics.append(
            {
                "name": require_resource_id(raw.get("name"), "metric.name"),
                "baseline": _number(raw.get("baseline"), "metric.baseline"),
                "target": _number(raw.get("target"), "metric.target"),
                "direction": direction,
            }
        )
    rollback = _object(request.get("rollback"), "rollback")
    _exact(
        rollback,
        "rollback",
        allowed={"previous_version", "trigger", "procedure"},
        required={"previous_version", "trigger", "procedure"},
    )
    normalized_rollback = {
        "previous_version": require_resource_id(
            rollback.get("previous_version"), "rollback.previous_version"
        ),
        "trigger": require_text(rollback.get("trigger"), "rollback.trigger", maximum=2048),
        "procedure": _strings(rollback.get("procedure"), "rollback.procedure"),
    }
    history = _objects(request.get("history", []), "history", allow_empty=True)
    normalized_history: list[dict[str, str]] = []
    seen_versions: set[str] = set()
    for raw in history:
        _exact(
            raw,
            "knowledge history",
            allowed={"version", "sha256", "disposition"},
            required={"version", "sha256", "disposition"},
        )
        historical_version = require_resource_id(raw.get("version"), "history.version")
        if historical_version in seen_versions or historical_version == version:
            raise ContractError("knowledge history versions must be unique and prior")
        seen_versions.add(historical_version)
        normalized_history.append(
            {
                "version": historical_version,
                "sha256": _sha256(raw.get("sha256"), "history.sha256"),
                "disposition": require_resource_id(
                    raw.get("disposition"), "history.disposition"
                ),
            }
        )
    if normalized_history and normalized_rollback["previous_version"] not in seen_versions:
        raise ContractError("rollback.previous_version must be present in knowledge history")
    proposal = {
        "scope": normalized_scope,
        "version": version,
        "sources": normalized_sources,
        "rules": normalized_rules,
        "metrics": normalized_metrics,
        "rollback": normalized_rollback,
        "history": normalized_history,
    }
    proposal["proposal_digest"] = digest_json(proposal)
    receipt_fields = sorted(
        _object(
            request.get("trusted_external_source_receipt", {}),
            "trusted_external_source_receipt",
        )
    )
    return _result(
        "BLOCKED" if external_sources else "PARTIAL",
        "TRUSTED_LEARNING_SOURCE_REQUIRED"
        if external_sources
        else "KNOWLEDGE_UPDATE_PROPOSED",
        {
            "proposal": proposal,
            "external_source_ids": external_sources,
            "caller_source_receipt_fields_observed": receipt_fields,
            "caller_source_receipt_accepted": False,
            "trusted_external_source_receipt": "NOT_RUN",
            "candidate_persisted": False,
            "persistence": "NOT_RUN",
            "enabled": False,
            "rollback_executed": False,
        },
    )


_PATH_RISK_MARKERS: Final = frozenset(
    {"auth", "security", "payment", "billing", "migration", "policy", "secrets"}
)
_SEMANTIC_RISK_MARKERS: Final = frozenset(
    {
        "authorization",
        "tenant-isolation",
        "money",
        "schema-change",
        "data-deletion",
        "external-side-effect",
    }
)
_ROLE_MATRIX: Final = MappingProxyType(
    {
        "LOW": ("code-owner",),
        "MEDIUM": ("code-owner", "qa-reviewer"),
        "HIGH": ("code-owner", "qa-reviewer", "security-reviewer"),
        "CRITICAL": (
            "code-owner",
            "qa-reviewer",
            "security-reviewer",
            "independent-approver",
        ),
    }
)


def authorize_governed_action(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate authorization evidence locally while always deferring authority."""

    request = _object(inputs, "authorization request")
    _exact(
        request,
        "authorization request",
        allowed={
            "_runtime_context",
            "resource_tenant_id",
            "action",
            "evaluation_time",
            "risk",
            "approvals",
            "exception",
            "budget",
            "retention",
            "access_policy",
            "trusted_policy_receipt",
        },
        required={
            "_runtime_context",
            "resource_tenant_id",
            "action",
            "evaluation_time",
            "risk",
            "budget",
            "retention",
            "access_policy",
        },
    )
    context = _validated_runtime_context(request, require_actor=True)
    actor_id = require_resource_id(context.get("actor_id"), "runtime.actor_id")
    actor_tenant = require_resource_id(context.get("tenant_id"), "runtime.tenant_id")
    resource_tenant = require_resource_id(
        request.get("resource_tenant_id"), "resource_tenant_id"
    )
    action = require_resource_id(request.get("action"), "action")
    evaluation_time_text = require_text(
        request.get("evaluation_time"), "evaluation_time", maximum=64
    )
    evaluation_time = _timestamp(evaluation_time_text, "evaluation_time")
    risk = _object(request.get("risk"), "risk")
    _exact(
        risk,
        "risk",
        allowed={"paths", "semantic_tags", "data_classification"},
        required={"paths", "semantic_tags", "data_classification"},
    )
    paths = [
        _path(value, "risk.paths[]")
        for value in _strings(risk.get("paths"), "risk.paths", allow_empty=True)
    ]
    semantic_tags = [
        require_resource_id(value, "risk.semantic_tags[]").casefold()
        for value in _strings(
            risk.get("semantic_tags"), "risk.semantic_tags", allow_empty=True
        )
    ]
    classification = require_text(
        risk.get("data_classification"), "risk.data_classification"
    ).upper()
    if classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        raise ContractError("risk.data_classification is invalid")
    score = 1 if paths or semantic_tags else 0
    for repository_path in paths:
        tokens = {
            token
            for part in PurePosixPath(repository_path).parts
            for token in re.split(r"[^a-z0-9]+", part.casefold())
            if token
        }
        if tokens.intersection(_PATH_RISK_MARKERS):
            score = max(score, 2)
    if set(semantic_tags).intersection(_SEMANTIC_RISK_MARKERS):
        score = max(score, 2)
    score = max(score, {"PUBLIC": 0, "INTERNAL": 0, "CONFIDENTIAL": 2, "RESTRICTED": 3}[classification])
    risk_level = ("LOW", "MEDIUM", "HIGH", "CRITICAL")[score]
    required_roles = _ROLE_MATRIX[risk_level]
    approvals = _objects(request.get("approvals", []), "approvals", allow_empty=True)
    valid_roles: set[str] = set()
    approval_ids: set[str] = set()
    approval_actors: set[str] = set()
    blockers: list[str] = []
    for raw in approvals:
        _exact(
            raw,
            "approval",
            allowed={"approval_id", "role", "actor_id", "scope", "expires_at"},
            required={"approval_id", "role", "actor_id", "scope", "expires_at"},
        )
        approval_id = require_resource_id(raw.get("approval_id"), "approval.approval_id")
        approver = require_resource_id(raw.get("actor_id"), "approval.actor_id")
        role = require_resource_id(raw.get("role"), "approval.role")
        scope = require_resource_id(raw.get("scope"), "approval.scope")
        expires_at = _timestamp(raw.get("expires_at"), "approval.expires_at")
        if approval_id in approval_ids or approver in approval_actors:
            raise ContractError("approval IDs and actors must be unique")
        approval_ids.add(approval_id)
        approval_actors.add(approver)
        if approver == actor_id:
            blockers.append(f"{approval_id}:SELF_APPROVAL")
        elif scope != action:
            blockers.append(f"{approval_id}:SCOPE_MISMATCH")
        elif expires_at <= evaluation_time:
            blockers.append(f"{approval_id}:EXPIRED")
        else:
            valid_roles.add(role)
    missing_roles = sorted(set(required_roles) - valid_roles)
    if missing_roles:
        blockers.append("MISSING_ROLES:" + ",".join(missing_roles))
    if actor_tenant != resource_tenant:
        blockers.append("TENANT_MISMATCH")
    budget = _object(request.get("budget"), "budget")
    _exact(
        budget,
        "budget",
        allowed={"amount", "currency"},
        required={"amount", "currency"},
    )
    normalized_budget = {
        "amount": _number(budget.get("amount"), "budget.amount"),
        "currency": require_resource_id(budget.get("currency"), "budget.currency").upper(),
    }
    retention = _object(request.get("retention"), "retention")
    _exact(
        retention,
        "retention",
        allowed={"days", "legal_hold"},
        required={"days", "legal_hold"},
    )
    normalized_retention = {
        "days": _integer(retention.get("days"), "retention.days", maximum=36_500),
        "legal_hold": _boolean(retention.get("legal_hold"), "retention.legal_hold"),
    }
    access = _object(request.get("access_policy"), "access_policy")
    _exact(
        access,
        "access_policy",
        allowed={"allowed_roles", "purpose"},
        required={"allowed_roles", "purpose"},
    )
    normalized_access = {
        "allowed_roles": _ids(access.get("allowed_roles"), "access_policy.allowed_roles"),
        "purpose": require_resource_id(access.get("purpose"), "access_policy.purpose"),
    }
    exception = request.get("exception")
    normalized_exception: dict[str, Any] | None = None
    if exception is not None:
        exception_value = _object(exception, "exception")
        _exact(
            exception_value,
            "exception",
            allowed={
                "exception_id",
                "scope",
                "compensating_controls",
                "expires_at",
                "budget_amount",
            },
            required={
                "exception_id",
                "scope",
                "compensating_controls",
                "expires_at",
                "budget_amount",
            },
        )
        exception_expiry = _timestamp(exception_value.get("expires_at"), "exception.expires_at")
        exception_scope = require_resource_id(exception_value.get("scope"), "exception.scope")
        exception_budget = _number(
            exception_value.get("budget_amount"), "exception.budget_amount"
        )
        controls = _ids(
            exception_value.get("compensating_controls"),
            "exception.compensating_controls",
        )
        if exception_scope != action:
            blockers.append("EXCEPTION_SCOPE_MISMATCH")
        if exception_expiry <= evaluation_time:
            blockers.append("EXCEPTION_EXPIRED")
        if exception_budget > normalized_budget["amount"]:
            blockers.append("EXCEPTION_BUDGET_EXCEEDED")
        normalized_exception = {
            "exception_id": require_resource_id(
                exception_value.get("exception_id"), "exception.exception_id"
            ),
            "scope": exception_scope,
            "compensating_controls": controls,
            "expires_at": require_text(
                exception_value.get("expires_at"), "exception.expires_at", maximum=64
            ),
            "budget_amount": exception_budget,
        }
    receipt_fields = sorted(
        _object(request.get("trusted_policy_receipt", {}), "trusted_policy_receipt")
    )
    evaluation = {
        "action": action,
        "actor_id": actor_id,
        "risk_level": risk_level,
        "required_roles": list(required_roles),
        "locally_valid_roles": sorted(valid_roles),
        "blockers": blockers,
        "exception": normalized_exception,
        "budget": normalized_budget,
        "retention": normalized_retention,
        "access_policy": normalized_access,
        "audit_required": True,
    }
    evaluation["evaluation_digest"] = digest_json(evaluation)
    return _result(
        "BLOCKED",
        "LOCAL_POLICY_VALIDATION_FAILED"
        if blockers
        else "TRUSTED_POLICY_DECISION_REQUIRED",
        {
            "evaluation": evaluation,
            "allowed": False,
            "caller_policy_receipt_fields_observed": receipt_fields,
            "caller_policy_receipt_accepted": False,
            "trusted_policy_receipt": "NOT_RUN",
            "authorization_side_effect": "NOT_RUN",
        },
    )


# Exact source-operation wrappers keep integration names stable while the richer
# names above remain directly usable in focused unit tests.
def plan_shards(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return plan_distributed_execution(inputs)


def verify_evidence(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return evaluate_oracle_evidence(inputs)


def classify_flaky(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return classify_flakiness(inputs)


def triage_defects(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return triage_advanced_defects(inputs)


def plan_repair(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return plan_advanced_repair(inputs)


def analyze_impact(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return analyze_typed_impact(inputs)


def analyze_impact_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return analyze_typed_impact(inputs)


def build_report(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return build_structured_report(inputs)


def create_checkpoint(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return create_durable_store_contract(inputs)


def estimate_eta(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return estimate_runtime_cost(inputs)


def estimate_eta_contract(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return estimate_runtime_cost(inputs)


def propose_learning(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return propose_knowledge_update(inputs)


def authorize_action(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
    return authorize_governed_action(inputs)


ADVANCED_OPERATION_REGISTRY: Final = MappingProxyType(
    {
        "19-distributed-test-execution": plan_shards,
        "20-test-oracle-evidence": verify_evidence,
        "21-flaky-test-control": classify_flaky,
        "22-defect-triage-rca": triage_defects,
        "23-repair-planning": plan_repair,
        "26-impact-analysis-regression": analyze_impact,
        "27-mutation-property-fuzz-testing": plan_advanced_testing,
        "29-reporting-observability": build_report,
        "30-checkpoint-resume-idempotency": create_checkpoint,
        "31-runtime-cost-eta": estimate_eta,
        "34-continuous-learning-knowledge-base": propose_learning,
        "35-governance-approval-audit": authorize_action,
    }
)
