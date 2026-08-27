"""Reproducible confidence and multi-seed stability utilities."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("invalid successes/trials")
    if trials == 0:
        return 0.0, 1.0
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return (centre - margin) / denominator, (centre + margin) / denominator


def non_inferiority(candidate_successes: int, candidate_trials: int, baseline_successes: int, baseline_trials: int, *, margin: float, z: float = 1.6448536269514722) -> dict[str, Any]:
    if not 0 <= margin < 1:
        raise ValueError("margin must be in [0, 1)")
    if min(candidate_trials, baseline_trials) <= 0:
        return {"conclusive": False, "non_inferior": False, "reason": "insufficient trials"}
    candidate_rate = candidate_successes / candidate_trials
    baseline_rate = baseline_successes / baseline_trials
    difference = candidate_rate - baseline_rate
    standard_error = math.sqrt(candidate_rate * (1 - candidate_rate) / candidate_trials + baseline_rate * (1 - baseline_rate) / baseline_trials)
    lower = difference - z * standard_error
    return {"conclusive": True, "candidate_rate": candidate_rate, "baseline_rate": baseline_rate, "difference": difference, "one_sided_lower_bound": lower, "margin": margin, "non_inferior": lower >= -margin}


def multi_seed_stability(results: Iterable[dict[str, Any]], *, minimum_seeds: int = 3, only_probabilistic: bool = False) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[str(result.get("case_id", "unknown"))].append(result)
    rows: list[dict[str, Any]] = []
    unstable = 0
    insufficient = 0
    for case_id, items in sorted(grouped.items()):
        executable = [item for item in items if item.get("status") not in {"skipped", "unavailable"}]
        statuses = [item.get("status") for item in executable]
        seeds = {item.get("seed", item.get("evidence", {}).get("seed")) for item in items}
        seeds.discard(None)
        required = max([minimum_seeds if (not only_probabilistic or any(item.get("probabilistic") or item.get("required_seed_count", 1) > 1 for item in items)) else 1] + [int(item.get("required_seed_count", 1) or 1) for item in items])
        enough = len(seeds) >= required or len(items) >= required
        if required > 1 and not enough:
            insufficient += 1
        stable = len(set(statuses)) <= 1
        if not stable:
            unstable += 1
        durations = [float(item.get("duration_ms", 0) or 0) for item in items if float(item.get("duration_ms", 0) or 0) > 0]
        mean = statistics.fmean(durations) if durations else 0.0
        rows.append({"case_id": case_id, "runs": len(items), "distinct_seeds": len(seeds), "pass_rate": sum(item.get("status") == "passed" for item in executable) / len(executable) if executable else None, "pass_rate_95ci": dict(zip(("lower", "upper"), wilson_interval(sum(item.get("status") == "passed" for item in executable), len(executable)))), "status_stable": stable, "duration_cv": statistics.pstdev(durations) / mean if len(durations) > 1 and mean else 0.0, "required_seed_count": required, "minimum_seeds_met": enough})
    return {"case_count": len(rows), "unstable_case_count": unstable, "insufficient_seed_case_count": insufficient, "cases": rows}
