"""Performance budget and scale-tier evaluation."""

from __future__ import annotations

from typing import Any


DEFAULT_DIRECTIONS = {"latency_p50_ms": "max", "latency_p95_ms": "max", "latency_p99_ms": "max", "wall_clock_ms": "max", "peak_rss_mb": "max", "cpu_seconds": "max", "token_input": "max", "token_output": "max", "credit_usd": "max", "throughput_per_second": "min", "cache_hit_rate": "min"}


def evaluate_performance(candidate: dict[str, float], budgets: dict[str, dict[str, Any]], *, baseline: dict[str, float] | None = None) -> dict[str, Any]:
    baseline = baseline or {}
    results: list[dict[str, Any]] = []
    for metric, policy in budgets.items():
        actual = candidate.get(metric)
        if actual is None:
            results.append({"metric": metric, "state": "BLOCKED", "reason": "metric unavailable"})
            continue
        direction = policy.get("direction", DEFAULT_DIRECTIONS.get(metric, "max"))
        limit = policy.get("limit")
        state = "PASS"
        reasons: list[str] = []
        if limit is not None and ((direction == "max" and actual > limit) or (direction == "min" and actual < limit)):
            state = "FAIL"
            reasons.append(f"{actual} violates {direction} limit {limit}")
        baseline_value = baseline.get(metric)
        ratio = None
        max_ratio = policy.get("max_regression_ratio")
        if baseline_value not in {None, 0} and max_ratio is not None:
            ratio = actual / baseline_value if direction == "max" else baseline_value / actual if actual else float("inf")
            if ratio > max_ratio:
                state = "FAIL"
                reasons.append(f"regression ratio {ratio:.4f} > {max_ratio}")
        results.append({"metric": metric, "state": state, "actual": actual, "limit": limit, "direction": direction, "baseline": baseline_value, "regression_ratio": ratio, "reasons": reasons})
    return {"passed": all(item["state"] == "PASS" for item in results), "blocked": any(item["state"] == "BLOCKED" for item in results), "results": results}


def large_repository_tier(loc: int, module_count: int, build_minutes: float) -> str:
    if loc >= 1_000_000 or module_count >= 100 or build_minutes >= 60:
        return "L4-mega"
    if loc >= 500_000 or module_count >= 50 or build_minutes >= 30:
        return "L4-large"
    if loc >= 100_000 or module_count >= 15 or build_minutes >= 10:
        return "L3-medium"
    if loc >= 10_000 or module_count >= 3:
        return "L2-small-repository"
    return "L1-fixture"
