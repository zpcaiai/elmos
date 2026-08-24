from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ParityThresholds:
    stable_turn_cached_token_reuse: float = 0.90
    unexpected_full_prefix_miss: float = 0.02
    exact_rerun_weighted_reuse: float = 0.99
    small_edit_weighted_reuse: float = 0.90
    unnecessary_invalidation: float = 0.05
    environment_snapshot_hit: float = 0.95
    warm_start_p95_reduction: float = 0.80
    restart_artifact_reuse: float = 0.999
    stable_followup_wall_clock_saved: float = 0.70
    model_input_cost_saved: float = 0.80
    long_session_cached_token_reuse: float = 0.80
    false_hits: int = 0
    cross_tenant_hits: int = 0
    corrupt_executions: int = 0
    under_validated_publications: int = 0


_MINIMUM_METRICS = {
    "stable_turn_cached_token_reuse",
    "exact_rerun_weighted_reuse",
    "small_edit_weighted_reuse",
    "environment_snapshot_hit",
    "warm_start_p95_reduction",
    "restart_artifact_reuse",
    "stable_followup_wall_clock_saved",
    "model_input_cost_saved",
    "long_session_cached_token_reuse",
}
_MAXIMUM_METRICS = {"unexpected_full_prefix_miss", "unnecessary_invalidation"}
_ZERO_METRICS = {"false_hits", "cross_tenant_hits", "corrupt_executions", "under_validated_publications"}


def weighted_reuse(costs: Iterable[tuple[bool, float]]) -> float:
    entries = list(costs)
    total = sum(max(0.0, cost) for _, cost in entries)
    if total == 0:
        return 0.0
    avoided = sum(max(0.0, cost) for hit, cost in entries if hit)
    return avoided / total


def evaluate_metrics(
    metrics: Mapping[str, float | int],
    thresholds: ParityThresholds | None = None,
) -> dict[str, Any]:
    threshold_values = asdict(thresholds or ParityThresholds())
    failures: list[str] = []
    checks: dict[str, bool] = {}
    for name in sorted(_MINIMUM_METRICS):
        actual = float(metrics.get(name, -1.0))
        expected = float(threshold_values[name])
        checks[name] = actual >= expected
        if not checks[name]:
            failures.append(f"{name}: {actual:.6f} < minimum {expected:.6f}")
    for name in sorted(_MAXIMUM_METRICS):
        actual = float(metrics.get(name, float("inf")))
        expected = float(threshold_values[name])
        checks[name] = actual <= expected
        if not checks[name]:
            failures.append(f"{name}: {actual:.6f} > maximum {expected:.6f}")
    for name in sorted(_ZERO_METRICS):
        actual = int(metrics.get(name, -1))
        checks[name] = actual == 0
        if not checks[name]:
            failures.append(f"{name}: {actual} != 0")
    return {
        "mandatory_pass": not failures,
        "checks": checks,
        "failures": failures,
        "thresholds": threshold_values,
    }
