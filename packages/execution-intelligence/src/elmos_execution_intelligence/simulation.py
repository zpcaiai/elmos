"""Monte Carlo simulation of system token consumption, system wall-clock, and the human baseline.

Three rules are enforced structurally rather than by convention:

1. System ETA covers machine-autonomous work only. Human approval, human
   acceptance and credential waits are carried in ``human_assisted`` and are
   never folded into ``wall_clock_hours``.
2. The human baseline consumes the same task DAG and therefore the same
   Definition of Done as the system estimate.
3. Every number leaves as a distribution (P50/P80/P90/worst case), never a point.
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

from .io_utils import summarize

TOKEN_FIELDS = ("input", "cached_input", "cache_write", "output", "reasoning_output")
SYSTEM_EXCLUSIONS = (
    "human approvals",
    "human acceptance and review effort",
    "credential and access provisioning waits",
    "external business or vendor decisions",
)


def _triangular(rng: random.Random, low: float, mode: float, high: float) -> float:
    if high <= low:
        return low
    mode = min(max(mode, low), high)
    return rng.triangular(low, high, mode)


def _topological(tasks: list[dict[str, Any]]) -> list[str]:
    task_map = {task["id"]: task for task in tasks}
    indegree = {task_id: 0 for task_id in task_map}
    children: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for dependency in task.get("depends_on", []):
            if dependency not in task_map:
                raise ValueError(f"Task {task['id']} depends on unknown task {dependency}")
            indegree[task["id"]] += 1
            children[dependency].append(task["id"])
    queue = deque(sorted(task_id for task_id, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(tasks):
        raise ValueError("Task DAG contains a cycle")
    return order


def _sample_task_runtime(task: dict[str, Any], rng: random.Random) -> float:
    system = task["system"]
    duration = _triangular(
        rng,
        float(system["optimistic_minutes"]),
        float(system["most_likely_minutes"]),
        float(system["pessimistic_minutes"]),
    )
    if rng.random() < float(system.get("rework_probability", 0.0)):
        low = float(system.get("rework_multiplier_min", 0.20))
        high = float(system.get("rework_multiplier_max", max(low, 1.0)))
        duration *= 1.0 + rng.uniform(low, max(low, high))
    if rng.random() < float(system.get("failure_probability", 0.0)):
        duration += _triangular(
            rng,
            float(system.get("recovery_optimistic_minutes", 1.0)),
            float(system.get("recovery_most_likely_minutes", 5.0)),
            float(system.get("recovery_pessimistic_minutes", 30.0)),
        )
    return max(0.0, duration)


def _sample_task_tokens(task: dict[str, Any], rng: random.Random) -> dict[str, float]:
    system = task.get("system", {})
    profile = system.get("token_profile", {})
    multiplier = _triangular(
        rng,
        float(profile.get("uncertainty_min", 0.80)),
        float(profile.get("uncertainty_mode", 1.00)),
        float(profile.get("uncertainty_max", 1.80)),
    )
    if rng.random() < float(system.get("rework_probability", 0.0)):
        low = float(system.get("rework_multiplier_min", 0.20))
        high = float(system.get("rework_multiplier_max", max(low, 1.0)))
        multiplier *= 1.0 + rng.uniform(low, max(low, high))
    sample = {field: float(profile.get(field, 0.0)) * multiplier for field in TOKEN_FIELDS}
    sample["total"] = sum(sample[field] for field in TOKEN_FIELDS)
    return sample


def _critical_path(tasks: list[dict[str, Any]], durations: dict[str, float], order: list[str]) -> float:
    task_map = {task["id"]: task for task in tasks}
    finish: dict[str, float] = {}
    for task_id in order:
        start = max((finish[dep] for dep in task_map[task_id].get("depends_on", [])), default=0.0)
        finish[task_id] = start + durations[task_id]
    return max(finish.values(), default=0.0)


def _schedule(tasks: list[dict[str, Any]], durations: dict[str, float], capacity: float) -> float:
    """List-schedule the DAG onto a pool of fractional worker capacity."""
    task_map = {task["id"]: task for task in tasks}
    children: dict[str, list[str]] = defaultdict(list)
    remaining: dict[str, int] = {}
    for task in tasks:
        remaining[task["id"]] = len(task.get("depends_on", []))
        for dependency in task.get("depends_on", []):
            children[dependency].append(task["id"])

    ready: list[tuple[float, int, str]] = []
    for task in tasks:
        units = float(task.get("system", {}).get("worker_units", 1.0))
        if units > capacity + 1e-9:
            raise ValueError(
                f"Task {task['id']} needs {units} worker units but effective capacity is {capacity:.3f}"
            )
        if remaining[task["id"]] == 0:
            heapq.heappush(ready, (-durations[task["id"]], -int(task.get("priority", 0)), task["id"]))

    running: list[tuple[float, str, float]] = []
    time = 0.0
    used = 0.0
    completed = 0
    total = len(tasks)

    while completed < total:
        deferred: list[tuple[float, int, str]] = []
        while ready:
            item = heapq.heappop(ready)
            task_id = item[2]
            units = float(task_map[task_id].get("system", {}).get("worker_units", 1.0))
            if used + units <= capacity + 1e-9:
                heapq.heappush(running, (time + durations[task_id], task_id, units))
                used += units
            else:
                deferred.append(item)
        for item in deferred:
            heapq.heappush(ready, item)

        if not running:
            raise ValueError("Scheduler deadlock: nothing running and nothing schedulable")

        next_time = running[0][0]
        time = next_time
        while running and abs(running[0][0] - next_time) < 1e-9:
            _, task_id, units = heapq.heappop(running)
            used -= units
            completed += 1
            for child in children[task_id]:
                remaining[child] -= 1
                if remaining[child] == 0:
                    heapq.heappush(ready, (-durations[child], -int(task_map[child].get("priority", 0)), child))
    return time


def effective_capacity(system: dict[str, Any]) -> float:
    raw = (
        float(system["workers"])
        * float(system["worker_availability"])
        * float(system["parallel_efficiency"])
        * float(system["model_concurrency_factor"])
        * float(system["code_conflict_factor"])
    )
    return max(1.0, raw)


def simulate_system(
    project: dict[str, Any], task_document: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, float]], dict[str, list[dict[str, float]]]]:
    tasks = task_document["tasks"]
    simulation = project.get("simulation", {})
    runs = int(simulation.get("runs", 5000))
    rng = random.Random(  # noqa: S311 - Monte Carlo, not cryptography; seeded on purpose
        int(simulation.get("seed", 42)))
    system = project["system"]
    capacity = effective_capacity(system)
    overhead = 1.0 + float(system.get("global_overhead_ratio", 0.0))
    worst_probability = float(system.get("worst_case_quantile", 0.99))
    order = _topological(tasks)

    wall_clock_hours: list[float] = []
    active_worker_hours: list[float] = []
    critical_path_hours: list[float] = []
    token_samples: list[dict[str, float]] = []
    per_task_tokens: dict[str, list[dict[str, float]]] = {task["id"]: [] for task in tasks}

    for _ in range(runs):
        durations = {task["id"]: _sample_task_runtime(task, rng) for task in tasks}
        wall_minutes = _schedule(tasks, durations, capacity) * overhead
        active_minutes = overhead * sum(
            durations[task["id"]] * float(task.get("system", {}).get("worker_units", 1.0)) for task in tasks
        )
        critical_minutes = _critical_path(tasks, durations, order) * overhead
        wall_clock_hours.append(wall_minutes / 60.0)
        active_worker_hours.append(active_minutes / 60.0)
        critical_path_hours.append(critical_minutes / 60.0)

        run_total = {field: 0.0 for field in TOKEN_FIELDS}
        run_total["total"] = 0.0
        for task in tasks:
            sample = _sample_task_tokens(task, rng)
            per_task_tokens[task["id"]].append(sample)
            for key in run_total:
                run_total[key] += sample[key]
        token_samples.append(run_total)

    runtime: dict[str, Any] = {
        "runs": runs,
        "seed": int(simulation.get("seed", 42)),
        "configured_workers": system["workers"],
        "effective_worker_capacity": round(capacity, 3),
        "global_overhead_ratio": float(system.get("global_overhead_ratio", 0.0)),
        "wall_clock_hours": summarize(wall_clock_hours, worst_probability),
        "active_worker_hours": summarize(active_worker_hours, worst_probability),
        "critical_path_hours": summarize(critical_path_hours, worst_probability),
        "scope": "machine-autonomous execution only",
        "excludes": list(SYSTEM_EXCLUSIONS),
    }
    if system.get("start_at"):
        start_at = datetime.fromisoformat(str(system["start_at"]).replace("Z", "+00:00"))
        runtime["expected_completion_at"] = {
            label: (start_at + timedelta(hours=float(runtime["wall_clock_hours"][label]))).isoformat()
            for label in ("p50", "p80", "p90", "worst_case")
        }
    return runtime, token_samples, per_task_tokens


def summarize_tokens(token_samples: list[dict[str, float]], worst_probability: float = 0.99) -> dict[str, Any]:
    fields = list(TOKEN_FIELDS) + ["total"]
    summary: dict[str, Any] = {
        field: summarize([sample[field] for sample in token_samples], worst_probability, digits=0)
        for field in fields
    }
    summary["category_sum_equals_total"] = True
    summary["accounting_rule"] = (
        "input/cached_input/cache_write/output/reasoning_output are disjoint categories; "
        "total is their sum and must never be added back to a category."
    )
    return summary


def summarize_task_tokens(
    per_task_tokens: dict[str, list[dict[str, float]]],
    tasks: list[dict[str, Any]],
    worst_probability: float = 0.99,
) -> list[dict[str, Any]]:
    names = {task["id"]: task.get("name", task["id"]) for task in tasks}
    rows = []
    for task_id, samples in per_task_tokens.items():
        totals = [sample["total"] for sample in samples]
        rows.append({
            "task_id": task_id,
            "name": names.get(task_id, task_id),
            "total_tokens": summarize(totals, worst_probability, digits=0),
            "by_category": {
                field: summarize([sample[field] for sample in samples], worst_probability, digits=0)
                for field in TOKEN_FIELDS
            },
        })
    rows.sort(key=lambda row: (-row["total_tokens"]["p50"], row["task_id"]))
    return rows


def _sample_human_task(task: dict[str, Any], rng: random.Random) -> dict[str, float]:
    human = task["human"]
    multiplier = _triangular(
        rng,
        float(human.get("uncertainty_min", 0.80)),
        float(human.get("uncertainty_mode", 1.00)),
        float(human.get("uncertainty_max", 1.60)),
    )
    return {role: float(hours) * multiplier for role, hours in human["hours_by_role"].items()}


def simulate_human(project: dict[str, Any], task_document: dict[str, Any]) -> dict[str, Any]:
    tasks = task_document["tasks"]
    simulation = project.get("simulation", {})
    runs = int(simulation.get("runs", 5000))
    seed = int(simulation.get("seed", 42)) + 100_003
    rng = random.Random(  # noqa: S311 - Monte Carlo, not cryptography; seeded on purpose
        seed)
    human = project["human"]
    focus = float(human.get("focus_ratio", 0.68))
    if not 0.0 < focus <= 1.0:
        raise ValueError("human.focus_ratio must be within (0, 1]")
    overhead = 1.0 + sum(
        float(human.get(key, 0.0))
        for key in ("review_overhead_ratio", "coordination_overhead_ratio", "rework_overhead_ratio")
    )
    hours_per_day = float(human.get("work_hours_per_day", 8))
    work_hours_per_week = hours_per_day * float(human.get("work_days_per_week", 5))
    month_working_days = float(human.get("month_working_days", 20))
    worst_probability = float(project.get("system", {}).get("worst_case_quantile", 0.99))
    role_configs = human["roles"]
    order = _topological(tasks)
    task_map = {task["id"]: task for task in tasks}

    person_hours_samples: list[float] = []
    calendar_weeks_samples: list[float] = []
    critical_path_samples: list[float] = []
    role_hour_samples: dict[str, list[float]] = {role: [] for role in role_configs}

    for _ in range(runs):
        sampled = {task["id"]: _sample_human_task(task, rng) for task in tasks}
        role_totals = {role: 0.0 for role in role_configs}
        for task_roles in sampled.values():
            for role, hours in task_roles.items():
                role_totals[role] = role_totals.get(role, 0.0) + hours * overhead

        role_load_hours = 0.0
        for role, total_hours in role_totals.items():
            headcount = float(role_configs[role]["headcount"])
            role_load_hours = max(role_load_hours, total_hours / max(headcount * focus, 1e-9))

        finish: dict[str, float] = {}
        for task_id in order:
            duration = 0.0
            for role, hours in sampled[task_id].items():
                headcount = float(role_configs[role]["headcount"])
                duration = max(duration, hours * overhead / max(headcount * focus, 1e-9))
            start = max((finish[dep] for dep in task_map[task_id].get("depends_on", [])), default=0.0)
            finish[task_id] = start + duration
        critical_path = max(finish.values(), default=0.0)

        team_work_hours = max(role_load_hours, critical_path)
        person_hours_samples.append(sum(role_totals.values()))
        calendar_weeks_samples.append(team_work_hours / max(work_hours_per_week, 1e-9))
        critical_path_samples.append(critical_path)
        for role in role_configs:
            role_hour_samples[role].append(role_totals.get(role, 0.0))

    person_summary = summarize(person_hours_samples, worst_probability)
    return {
        "runs": runs,
        "seed": seed,
        "person_hours": person_summary,
        "person_days": {key: round(value / hours_per_day, 3) for key, value in person_summary.items()},
        "person_months": {
            key: round(value / (hours_per_day * month_working_days), 3) for key, value in person_summary.items()
        },
        "calendar_weeks": summarize(calendar_weeks_samples, worst_probability),
        "critical_path_work_hours": summarize(critical_path_samples, worst_probability),
        "role_person_hours": {
            role: summarize(values, worst_probability) for role, values in sorted(role_hour_samples.items())
        },
        "team": {role: config["headcount"] for role, config in sorted(role_configs.items())},
        "overhead_multiplier": round(overhead, 4),
        "focus_ratio": focus,
        "same_definition_of_done": True,
    }
