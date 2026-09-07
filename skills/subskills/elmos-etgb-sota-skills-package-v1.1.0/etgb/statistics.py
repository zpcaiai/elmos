from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("invalid successes/trials")
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return ((centre - margin) / denominator, (centre + margin) / denominator)


def non_inferiority(
    candidate_successes: int,
    candidate_trials: int,
    baseline_successes: int,
    baseline_trials: int,
    *,
    margin: float,
    z: float = 1.6448536269514722,
) -> dict[str, Any]:
    if not 0 <= margin < 1:
        raise ValueError("margin must be in [0, 1)")
    if min(candidate_trials, baseline_trials) <= 0:
        return {"conclusive": False, "non_inferior": False, "reason": "insufficient trials"}
    pc = candidate_successes / candidate_trials
    pb = baseline_successes / baseline_trials
    diff = pc - pb
    se = math.sqrt(pc * (1 - pc) / candidate_trials + pb * (1 - pb) / baseline_trials)
    lower = diff - z * se
    return {
        "conclusive": True,
        "candidate_rate": pc,
        "baseline_rate": pb,
        "difference": diff,
        "one_sided_lower_bound": lower,
        "margin": margin,
        "non_inferior": lower >= -margin,
    }


def multi_seed_stability(
    results: Iterable[dict[str, Any]],
    *,
    minimum_seeds: int = 3,
    only_probabilistic: bool = False,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[result.get("case_id", "unknown")].append(result)
    cases: list[dict[str, Any]] = []
    unstable = 0
    insufficient = 0
    for case_id, rows in sorted(grouped.items()):
        statuses = [row.get("status") for row in rows]
        executable = [status for status in statuses if status not in {"skipped", "unavailable"}]
        passed = sum(status == "passed" for status in executable)
        durations = [float(row.get("duration_ms", 0) or 0) for row in rows if float(row.get("duration_ms", 0) or 0) > 0]
        seeds = {row.get("seed", row.get("evidence", {}).get("seed")) for row in rows}
        seeds.discard(None)
        stable_status = len(set(executable)) <= 1
        duration_cv = statistics.pstdev(durations) / statistics.fmean(durations) if len(durations) > 1 and statistics.fmean(durations) else 0.0
        seed_required = not only_probabilistic or any(
            bool(row.get("probabilistic"))
            or int(row.get("required_seed_count", 1) or 1) > 1
            or bool(row.get("evidence", {}).get("probabilistic"))
            for row in rows
        )
        required = max(
            [minimum_seeds if seed_required else 1]
            + [int(row.get("required_seed_count", 1) or 1) for row in rows]
        )
        enough = (len(seeds) >= required or len(rows) >= required) if seed_required else True
        if seed_required and not enough:
            insufficient += 1
        if not stable_status:
            unstable += 1
        interval = wilson_interval(passed, len(executable)) if executable else (0.0, 1.0)
        cases.append(
            {
                "case_id": case_id,
                "runs": len(rows),
                "distinct_seeds": len(seeds),
                "pass_rate": passed / len(executable) if executable else None,
                "pass_rate_95ci": {"lower": interval[0], "upper": interval[1]},
                "status_stable": stable_status,
                "duration_cv": duration_cv,
                "seed_required": seed_required,
                "required_seed_count": required,
                "minimum_seeds_met": enough,
            }
        )
    return {
        "case_count": len(cases),
        "unstable_case_count": unstable,
        "insufficient_seed_case_count": insufficient,
        "cases": cases,
    }
