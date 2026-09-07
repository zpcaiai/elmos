"""Skill 02 — task decomposition engine.

Derives a task DAG from a scope baseline instead of having one hand-typed. Every
duration and token figure is `base + coefficient x driver`, where the drivers are
measured facts (route count, language count, corpus size) and the coefficients
live in ``config/decomposition-model.json``.

That separation is the whole point: when the numbers turn out wrong, the fix is a
config change plus `calibrate`, not an edit buried in a hand-written DAG that
nobody can reconstruct the reasoning for.
"""
from __future__ import annotations

from typing import Any

from .io_utils import quantile

TOKEN_FIELDS = ("input", "cached_input", "cache_write", "output", "reasoning_output")


def compute_drivers(baseline: dict[str, Any]) -> dict[str, float]:
    """Extract the measurable quantities the sizing model is allowed to use."""
    inventory = baseline.get("route_matrix") or {}
    routes = float(inventory.get("declared_route_count") or 0)
    matrix_languages = inventory.get("languages") or []
    languages = float(len(matrix_languages) or baseline.get("language_count") or 0)
    pending = list(inventory.get("pending_analyzer_languages") or [])

    # A route touches a pending language if either endpoint is pending. For a
    # complete directed permutation that is n*(n-1) - (n-p)*(n-p-1).
    if languages and pending:
        n = int(languages)
        p = len(pending)
        pending_routes = float(n * (n - 1) - (n - p) * (n - p - 1))
    else:
        pending_routes = 0.0

    corpus = baseline.get("corpus", {})
    return {
        "routes": routes or 1.0,
        "languages": languages or 1.0,
        "pending_languages": float(len(pending)),
        "pending_routes": pending_routes,
        "language_pairs": max(0.0, languages * (languages - 1)),
        "corpus_mtokens": float(corpus.get("estimated_tokens", 0)) / 1_000_000.0,
        "kfiles": float(corpus.get("files", 0)) / 1_000.0,
    }


def _size(spec: dict[str, Any], drivers: dict[str, float]) -> float:
    value = float(spec.get("base", 0.0))
    for driver, coefficient in (spec.get("per") or {}).items():
        if driver not in drivers:
            raise ValueError(f"decomposition model references unknown driver '{driver}'")
        value += float(coefficient) * drivers[driver]
    if "floor" in spec:
        value = max(value, float(spec["floor"]))
    if "ceiling" in spec:
        value = min(value, float(spec["ceiling"]))
    return value


def _condition_met(when: dict[str, Any], drivers: dict[str, float]) -> bool:
    for key, threshold in when.items():
        if not key.startswith("min_"):
            raise ValueError(f"unsupported condition '{key}' (only min_<driver> is supported)")
        driver = key[len("min_"):]
        if driver not in drivers:
            raise ValueError(f"condition references unknown driver '{driver}'")
        if drivers[driver] < float(threshold):
            return False
    return True


def _token_profile(total: float, split: dict[str, float]) -> dict[str, float]:
    profile: dict[str, float] = {
        field: float(round(total * float(split[field]))) for field in TOKEN_FIELDS
    }
    profile.update({"uncertainty_min": 0.80, "uncertainty_mode": 1.00, "uncertainty_max": 1.80})
    return profile


def _human_hours(spec: dict[str, Any], drivers: dict[str, float]) -> dict[str, float]:
    return {role: round(_size(config, drivers), 2) for role, config in spec.items()}


def decompose(
    baseline: dict[str, Any],
    model: dict[str, Any],
    dag_id: str = "generated-dag",
) -> dict[str, Any]:
    drivers = compute_drivers(baseline)
    split = {field: model["token_split"][field] for field in TOKEN_FIELDS}
    total_split = sum(split.values())
    if abs(total_split - 1.0) > 1e-6:
        raise ValueError(f"token_split must sum to 1.0, got {total_split}")

    emitted: dict[str, list[str]] = {}
    tasks: list[dict[str, Any]] = []

    for template in model["templates"]:
        if not _condition_met(template.get("when", {}), drivers):
            emitted[template["id"]] = []
            continue

        per_item = template.get("per_item")
        items = [None]
        if per_item:
            inventory = baseline.get("route_matrix") or {}
            if per_item == "pending_languages":
                items = list(inventory.get("pending_analyzer_languages") or [])
            else:
                raise ValueError(f"unsupported per_item '{per_item}'")
            if not items:
                emitted[template["id"]] = []
                continue

        ids: list[str] = []
        for item in items:
            task_id = template["id"] if item is None else f"{template['id']}-{item}"
            name = template["name"].replace("{language}", str(item)) if item else template["name"]

            minutes = _size(template["minutes"], drivers)
            spread = template.get("spread", {"optimistic": 0.6, "pessimistic": 2.2})
            # A per-item template sizes one item; N pending languages therefore
            # produce N independent tasks, not one task split N ways.
            total_tokens = _size(template["total_tokens"], drivers)

            depends_on: list[str] = []
            for parent in template.get("depends_on", []):
                depends_on.extend(emitted.get(parent, []))

            recovery = template.get("recovery_minutes", [3, 12, 60])
            system = {
                "optimistic_minutes": round(minutes * float(spread["optimistic"]), 2),
                "most_likely_minutes": round(minutes, 2),
                "pessimistic_minutes": round(minutes * float(spread["pessimistic"]), 2),
                "worker_units": template.get("worker_units", 1),
                "rework_probability": template.get("rework_probability", 0.15),
                "rework_multiplier_min": template.get("rework_multiplier_min", 0.2),
                "rework_multiplier_max": template.get("rework_multiplier_max", 0.9),
                "failure_probability": template.get("failure_probability", 0.05),
                "recovery_optimistic_minutes": recovery[0],
                "recovery_most_likely_minutes": recovery[1],
                "recovery_pessimistic_minutes": recovery[2],
                "token_profile": _token_profile(total_tokens, split),
            }
            if "peak_context" in template:
                # Declared here so the router can enforce it; a task without it is
                # reported as unchecked rather than assumed to fit any window.
                system["peak_context_tokens"] = int(round(_size(template["peak_context"], drivers)))
            tasks.append({
                "id": task_id,
                "name": name,
                "depends_on": depends_on,
                "category": template["category"],
                "complexity": template["complexity"],
                "priority": template["priority"],
                "system": system,
                "human": {
                    "hours_by_role": _human_hours(template["human_hours"], drivers),
                    "uncertainty_min": 0.80,
                    "uncertainty_mode": 1.00,
                    "uncertainty_max": 1.70,
                },
                "derivation": {
                    "template": template["id"],
                    "item": item,
                    "minutes_formula": template["minutes"],
                    "total_tokens_formula": template["total_tokens"],
                },
            })
            ids.append(task_id)
        emitted[template["id"]] = ids

    return {
        "schema_version": "1.0.0",
        "dag_id": dag_id,
        "generated_for": baseline.get("root"),
        "generated_by": "decomposition-engine",
        "drivers": {key: round(value, 4) for key, value in drivers.items()},
        "model_version": model.get("version"),
        "provenance": [
            "Derived from a scope baseline; every duration and token figure is base + coefficient x driver.",
            "Coefficients live in config/decomposition-model.json and are seeds, not measurements.",
            "Run `calibrate` then `apply-calibration` after the first executed milestone.",
        ],
        "tasks": tasks,
    }


def critical_path_seed(task_document: dict[str, Any]) -> dict[str, Any]:
    """Longest dependency chain by most-likely duration, with no resource contention.

    This is a lower bound on wall-clock: adding workers cannot beat it. The
    Monte Carlo estimate will be longer because it also models contention,
    rework and recovery.
    """
    tasks = {task["id"]: task for task in task_document["tasks"]}
    memo: dict[str, tuple[float, list[str]]] = {}

    def walk(task_id: str, seen: frozenset[str]) -> tuple[float, list[str]]:
        if task_id in memo:
            return memo[task_id]
        if task_id in seen:
            raise ValueError("Task DAG contains a cycle")
        task = tasks[task_id]
        duration = float(task["system"]["most_likely_minutes"])
        best_length, best_path = 0.0, []
        for parent in task.get("depends_on", []):
            length, path = walk(parent, seen | {task_id})
            if length > best_length:
                best_length, best_path = length, path
        result = (best_length + duration, best_path + [task_id])
        memo[task_id] = result
        return result

    longest, path = 0.0, []
    for task_id in tasks:
        length, chain = walk(task_id, frozenset())
        if length > longest:
            longest, path = length, chain

    durations = [float(task["system"]["most_likely_minutes"]) for task in task_document["tasks"]]
    return {
        "schema_version": "1.0.0",
        "artifact": "critical-path-seed",
        "dag_id": task_document.get("dag_id"),
        "critical_path": path,
        "critical_path_minutes": round(longest, 2),
        "critical_path_hours": round(longest / 60.0, 3),
        "task_count": len(tasks),
        "total_task_minutes": round(sum(durations), 2),
        "median_task_minutes": round(quantile(durations, 0.5), 2),
        "max_theoretical_speedup": round(sum(durations) / longest, 3) if longest else None,
        "interpretation": (
            "This is the no-contention lower bound. The Monte Carlo wall-clock is longer because it "
            "adds worker contention, rework and recovery."
        ),
    }


def estimation_seed_rows(task_document: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for task in task_document["tasks"]:
        system = task["system"]
        profile = system["token_profile"]
        rows.append({
            "task_id": task["id"],
            "name": task["name"],
            "category": task["category"],
            "complexity": task["complexity"],
            "depends_on": ";".join(task.get("depends_on", [])),
            "worker_units": system["worker_units"],
            "optimistic_minutes": system["optimistic_minutes"],
            "most_likely_minutes": system["most_likely_minutes"],
            "pessimistic_minutes": system["pessimistic_minutes"],
            "rework_probability": system["rework_probability"],
            "failure_probability": system["failure_probability"],
            "total_tokens": sum(profile[field] for field in TOKEN_FIELDS),
            **{field: profile[field] for field in TOKEN_FIELDS},
            "human_hours_total": round(sum(task["human"]["hours_by_role"].values()), 2),
        })
    return rows
