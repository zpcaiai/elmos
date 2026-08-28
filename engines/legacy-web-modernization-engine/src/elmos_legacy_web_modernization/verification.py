"""Typed behavioral, runtime and trace verification oracles."""

from __future__ import annotations

import hashlib
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .canonical import canonical_digest, finite_json

DIMENSIONS: tuple[str, ...] = (
    "route",
    "protocol",
    "view",
    "binding",
    "validation",
    "navigation",
    "session",
    "security",
    "transaction",
    "database",
    "externalEffects",
    "concurrency",
    "performance",
)
CRITICAL_DIMENSIONS = frozenset(
    {"security", "session", "transaction", "database", "externalEffects"}
)
NORMALIZER_PATHS: Mapping[str, frozenset[str]] = {
    "NORM-TRACE-ID": frozenset({"traceId", "trace_id", "x-trace-id", "correlationId"}),
    "NORM-SESSION-ID": frozenset({"sessionId", "session_id", "jsessionid"}),
    "NORM-TIMESTAMP": frozenset({"timestamp", "createdAt", "updatedAt", "date"}),
}


class VerificationError(ValueError):
    pass


def _normalize(value: Any, normalizers: Sequence[str], applied: set[str]) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key in sorted(value, key=str):
            key_text = str(key)
            replacement = None
            for normalizer in normalizers:
                if key_text.lower() in {
                    item.lower() for item in NORMALIZER_PATHS[normalizer]
                }:
                    replacement = f"<{normalizer.lower()}>"
                    applied.add(normalizer)
                    break
            result[key_text] = (
                replacement
                if replacement is not None
                else _normalize(value[key], normalizers, applied)
            )
        return result
    if isinstance(value, list):
        # Lists remain order-sensitive: invocation, redirect and effect order is
        # semantic in a legacy web application.
        return [_normalize(item, normalizers, applied) for item in value]
    return value


def _dimension_record(
    *, equivalent: bool = False, normalized: bool = False, unknown: bool = False
) -> dict[str, Any]:
    return {
        "denominator": 1,
        "verified": 0 if unknown else 1,
        "equivalent": int(equivalent and not normalized),
        "normalizedEquivalent": int(normalized),
        "mismatch": int(not equivalent and not normalized and not unknown),
        "unknown": int(unknown),
        "confidence": 0.0 if unknown else 1.0,
    }


def evaluate_equivalence(
    inputs: Mapping[str, Any], *, oracle_kind: str
) -> dict[str, Any]:
    observations = inputs.get("observations")
    mode = str(inputs.get("equivalence_mode", "strict"))
    if mode not in {"strict", "normalized", "hardened"}:
        raise VerificationError(
            "equivalence_mode must be strict, normalized or hardened"
        )
    requested = inputs.get("normalizers", [])
    if not isinstance(requested, list) or any(
        item not in NORMALIZER_PATHS for item in requested
    ):
        raise VerificationError("only approved normalizers may be used")
    if (
        not isinstance(observations, Mapping)
        or not isinstance(observations.get("legacy"), Mapping)
        or not isinstance(observations.get("target"), Mapping)
    ):
        return {
            "reportVersion": "2.0.0",
            "mode": mode,
            "legacyArtifact": "NOT_RUN",
            "targetArtifact": "NOT_RUN",
            "dimensions": {
                name: _dimension_record(unknown=True) for name in DIMENSIONS
            },
            "mismatches": [],
            "summary": {
                "equivalence": 0.0,
                "criticalMismatches": 0,
                "unknowns": len(DIMENSIONS),
            },
            "gate": {
                "status": "blocked",
                "blockingReasons": ["legacy and target observations are required"],
            },
        }
    legacy = finite_json(dict(observations["legacy"]))
    target = finite_json(dict(observations["target"]))
    dimensions: dict[str, Any] = {}
    mismatches: list[dict[str, Any]] = []
    applied_normalizers: set[str] = set()
    for dimension in DIMENSIONS:
        left = legacy.get(dimension)
        right = target.get(dimension)
        if left is None or right is None:
            dimensions[dimension] = _dimension_record(unknown=True)
            continue
        exact = left == right
        normalized = False
        normalizer_for_mismatch: str | None = None
        if not exact and mode in {"normalized", "hardened"} and requested:
            before = set(applied_normalizers)
            left_normalized = _normalize(deepcopy(left), requested, applied_normalizers)
            right_normalized = _normalize(
                deepcopy(right), requested, applied_normalizers
            )
            normalized = left_normalized == right_normalized
            used = sorted(applied_normalizers - before)
            normalizer_for_mismatch = ",".join(used) if used else None
        hardened = False
        if (
            not exact
            and not normalized
            and mode == "hardened"
            and dimension == "security"
        ):
            left_decision = left.get("decision") if isinstance(left, Mapping) else None
            right_decision = (
                right.get("decision") if isinstance(right, Mapping) else None
            )
            rank = {"allow": 0, "challenge": 1, "deny": 2}
            hardened = (
                left_decision in rank
                and right_decision in rank
                and rank[right_decision] > rank[left_decision]
            )
            normalized = hardened
            normalizer_for_mismatch = (
                "SECURITY-HARDENING-ALLOWLIST" if hardened else normalizer_for_mismatch
            )
        dimensions[dimension] = _dimension_record(
            equivalent=exact or normalized, normalized=normalized
        )
        if not exact and not normalized:
            mismatch_id = hashlib.sha256(
                canonical_digest(
                    {"dimension": dimension, "left": left, "right": right}
                ).encode()
            ).hexdigest()[:16]
            mismatches.append(
                {
                    "id": "mismatch:" + mismatch_id,
                    "scenarioId": str(
                        observations.get("scenarioId", "scenario:provided")
                    ),
                    "dimension": dimension,
                    "severity": "critical"
                    if dimension in CRITICAL_DIMENSIONS
                    else "high",
                    "classification": "order-or-value-difference",
                    "firstDivergence": {"dimension": dimension},
                    "legacyObservationRef": "observation://legacy/" + dimension,
                    "targetObservationRef": "observation://target/" + dimension,
                    "normalizerApplied": normalizer_for_mismatch,
                    "rootCauseId": None,
                }
            )
    verified = sum(item["verified"] for item in dimensions.values())
    equivalent = sum(
        item["equivalent"] + item["normalizedEquivalent"]
        for item in dimensions.values()
    )
    critical = sum(item["severity"] == "critical" for item in mismatches)
    unknowns = sum(item["unknown"] for item in dimensions.values())
    blocking = (["critical mismatch"] if critical else []) + (
        ["unverified dimensions"] if unknowns else []
    )
    return {
        "reportVersion": "2.0.0",
        "mode": mode,
        "legacyArtifact": str(
            observations.get("legacyArtifact", "observation://legacy")
        ),
        "targetArtifact": str(
            observations.get("targetArtifact", "observation://target")
        ),
        "environment": {
            "class": "isolated-observation",
            "clock": str(observations.get("clock", "controlled")),
            "oracle": oracle_kind,
            "normalization": {
                "requested": list(requested),
                "applied": sorted(applied_normalizers),
                "orderSensitive": True,
            },
        },
        "dimensions": dimensions,
        "mismatches": mismatches,
        "summary": {
            "equivalence": equivalent / verified if verified else 0.0,
            "criticalMismatches": critical,
            "unknowns": unknowns,
        },
        "gate": {
            "status": "passed" if not mismatches and not unknowns else "failed",
            "blockingReasons": blocking,
        },
    }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def evaluate_runtime_workload(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate bounded, caller-captured load/fault samples deterministically."""

    workload = inputs.get("runtime_observations")
    if not isinstance(workload, Mapping):
        return {
            "reportVersion": "1.0.0",
            "status": "blocked",
            "reason": "runtime_observations are required",
            "scenarios": [
                "parallel-session",
                "threadlocal-cleanup",
                "async-dispatch",
                "timeout",
                "connection-pool-exhaustion",
            ],
            "execution": "NOT_RUN",
            "gate": {
                "status": "blocked",
                "blockingReasons": ["real runtime observations missing"],
            },
        }
    thresholds = inputs.get("runtime_thresholds", {})
    if not isinstance(thresholds, Mapping):
        raise VerificationError("runtime_thresholds must be an object")
    max_error_rate = float(thresholds.get("maxErrorRate", 0.01))
    max_p95_ratio = float(thresholds.get("maxP95Ratio", 1.20))
    sides: dict[str, Any] = {}
    for side in ("legacy", "target"):
        samples = workload.get(side)
        if not isinstance(samples, list) or not samples or len(samples) > 100_000:
            raise VerificationError(
                f"{side} runtime samples must be a bounded non-empty array"
            )
        durations: list[float] = []
        failures = 0
        leaked_sessions = 0
        for item in samples:
            if not isinstance(item, Mapping):
                raise VerificationError("runtime sample must be an object")
            duration = item.get("durationMs")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or not math.isfinite(float(duration))
                or duration < 0
            ):
                raise VerificationError(
                    "runtime duration must be finite and non-negative"
                )
            durations.append(float(duration))
            failures += int(not bool(item.get("success", False)))
            leaked_sessions += int(bool(item.get("sessionLeak", False)))
        sides[side] = {
            "count": len(samples),
            "failures": failures,
            "errorRate": failures / len(samples),
            "sessionLeaks": leaked_sessions,
            "p50Ms": _percentile(durations, 0.50),
            "p95Ms": _percentile(durations, 0.95),
            "p99Ms": _percentile(durations, 0.99),
            "meanMs": statistics.fmean(durations),
        }
    ratio = (
        sides["target"]["p95Ms"] / sides["legacy"]["p95Ms"]
        if sides["legacy"]["p95Ms"]
        else (1.0 if sides["target"]["p95Ms"] == 0 else math.inf)
    )
    faults = workload.get("faults", [])
    if not isinstance(faults, list):
        raise VerificationError("faults must be an array")
    unrecovered = [
        str(item.get("id", "unknown"))
        for item in faults
        if isinstance(item, Mapping) and not item.get("recovered")
    ]
    blockers = []
    if sides["target"]["errorRate"] > max_error_rate:
        blockers.append("target error rate exceeds threshold")
    if sides["target"]["sessionLeaks"]:
        blockers.append("target session isolation leak")
    if ratio > max_p95_ratio:
        blockers.append("target p95 regression exceeds threshold")
    if unrecovered:
        blockers.append("unrecovered injected faults")
    return {
        "reportVersion": "1.0.0",
        "status": "passed" if not blockers else "failed",
        "execution": "CALLER_CAPTURED_RUNTIME_EVALUATED",
        "metrics": sides,
        "comparison": {"targetToLegacyP95Ratio": ratio},
        "faults": {"count": len(faults), "unrecovered": unrecovered},
        "thresholds": {"maxErrorRate": max_error_rate, "maxP95Ratio": max_p95_ratio},
        "gate": {
            "status": "passed" if not blockers else "failed",
            "blockingReasons": blockers,
        },
        "inputDigest": canonical_digest(workload),
    }


def correlate_traces(inputs: Mapping[str, Any]) -> dict[str, Any]:
    traces = inputs.get("traces")
    if not isinstance(traces, Mapping):
        return {
            "traceVersion": "1.0.0",
            "status": "blocked",
            "reason": "traces are required",
            "correlations": [],
            "gate": {
                "status": "blocked",
                "blockingReasons": ["trace observations missing"],
            },
        }
    grouped: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: {"legacy": [], "target": []}
    )
    for side in ("legacy", "target"):
        spans = traces.get(side)
        if not isinstance(spans, list):
            raise VerificationError(f"{side} traces must be an array")
        for span in spans:
            if not isinstance(span, Mapping) or not isinstance(
                span.get("correlationId"), str
            ):
                raise VerificationError("every span requires a correlationId")
            grouped[str(span["correlationId"])][side].append(span)
    correlations = []
    blockers = []
    for correlation_id in sorted(grouped):
        pair = grouped[correlation_id]
        legacy_names = [str(item.get("name")) for item in pair["legacy"]]
        target_names = [str(item.get("name")) for item in pair["target"]]
        status = (
            "equivalent"
            if legacy_names == target_names and legacy_names
            else "mismatch"
        )
        if status != "equivalent":
            blockers.append("trace sequence mismatch:" + correlation_id)
        correlations.append(
            {
                "correlationId": correlation_id,
                "legacySequence": legacy_names,
                "targetSequence": target_names,
                "status": status,
            }
        )
    return {
        "traceVersion": "1.0.0",
        "status": "passed" if not blockers else "failed",
        "correlations": correlations,
        "gate": {
            "status": "passed" if not blockers else "failed",
            "blockingReasons": blockers,
        },
    }
