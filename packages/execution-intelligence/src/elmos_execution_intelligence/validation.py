"""Input validation. A missing input produces BLOCKED with the missing item named -- never a guess."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
from typing import Any

TOKEN_FIELDS = ("input", "cached_input", "cache_write", "output", "reasoning_output")
VALID_MODES = {"generation", "conversion", "modernization", "migration", "verification"}


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def validate_project(project: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    _require(bool(project.get("project_id")), "project.project_id is required", errors)
    _require(
        project.get("mode") in VALID_MODES,
        "project.mode must be one of " + "/".join(sorted(VALID_MODES)),
        errors,
    )

    definition = project.get("definition_of_done")
    _require(isinstance(definition, dict), "project.definition_of_done must be an object", errors)
    if isinstance(definition, dict):
        _require(bool(definition.get("level")), "definition_of_done.level is required", errors)
        _require(isinstance(definition.get("checks", []), list), "definition_of_done.checks must be a list", errors)
        _require(bool(definition.get("checks")), "definition_of_done.checks must not be empty", errors)

    simulation = project.get("simulation", {})
    _require(_number(simulation.get("runs")), "simulation.runs is required", errors)
    if _number(simulation.get("runs")):
        _require(int(simulation["runs"]) >= 100, "simulation.runs must be >= 100 for stable quantiles", errors)

    system = project.get("system", {})
    for key in ("workers", "worker_availability", "parallel_efficiency",
                "model_concurrency_factor", "code_conflict_factor"):
        _require(key in system, f"system.{key} is required", errors)
    if _number(system.get("workers")):
        _require(float(system["workers"]) > 0, "system.workers must be > 0", errors)
    for key in ("worker_availability", "parallel_efficiency", "model_concurrency_factor", "code_conflict_factor"):
        if _number(system.get(key)):
            _require(0 < float(system[key]) <= 1, f"system.{key} must be within (0, 1]", errors)
    if _number(system.get("worst_case_quantile")):
        _require(0.5 <= float(system["worst_case_quantile"]) <= 1.0,
                 "system.worst_case_quantile must be within [0.5, 1.0]", errors)
    if system.get("start_at"):
        try:
            datetime.fromisoformat(str(system["start_at"]).replace("Z", "+00:00"))
        except ValueError:
            errors.append("system.start_at must be ISO-8601")

    human = project.get("human", {})
    roles = human.get("roles")
    _require(isinstance(roles, dict) and bool(roles), "human.roles is required and must be non-empty", errors)
    if isinstance(roles, dict):
        for role, config in roles.items():
            _require(
                _number(config.get("headcount")) and float(config["headcount"]) > 0,
                f"human.roles.{role}.headcount must be a number > 0",
                errors,
            )
    if _number(human.get("focus_ratio")):
        _require(0 < float(human["focus_ratio"]) <= 1, "human.focus_ratio must be within (0, 1]", errors)

    assisted = project.get("human_assisted", {})
    if _number(assisted.get("review_parallel_fraction")):
        _require(
            0 <= float(assisted["review_parallel_fraction"]) <= 1,
            "human_assisted.review_parallel_fraction must be within [0, 1]",
            errors,
        )
    if _number(project.get("confidence")):
        _require(0 <= float(project["confidence"]) <= 1, "project.confidence must be within [0, 1]", errors)
    return errors


def validate_tasks(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tasks = document.get("tasks")
    _require(isinstance(tasks, list) and bool(tasks), "tasks must be a non-empty list", errors)
    if not isinstance(tasks, list):
        return errors

    ids: set[str] = set()
    for index, task in enumerate(tasks):
        prefix = f"tasks[{index}]"
        task_id = task.get("id")
        _require(isinstance(task_id, str) and bool(task_id), f"{prefix}.id is required", errors)
        if isinstance(task_id, str) and task_id:
            _require(task_id not in ids, f"duplicate task id: {task_id}", errors)
            ids.add(task_id)
        _require(isinstance(task.get("depends_on", []), list), f"{prefix}.depends_on must be a list", errors)

        system = task.get("system", {})
        _require(isinstance(system, dict), f"{prefix}.system must be an object", errors)
        durations = ("optimistic_minutes", "most_likely_minutes", "pessimistic_minutes")
        for key in durations:
            _require(_number(system.get(key)), f"{prefix}.system.{key} is required and must be a number", errors)
        if all(_number(system.get(key)) for key in durations):
            low, mode, high = (float(system[key]) for key in durations)
            _require(
                0 <= low <= mode <= high,
                f"{prefix}.system requires 0 <= optimistic <= most_likely <= pessimistic",
                errors,
            )
        if "worker_units" in system:
            _require(_number(system["worker_units"]) and float(system["worker_units"]) > 0,
                     f"{prefix}.system.worker_units must be > 0", errors)
        for key in ("rework_probability", "failure_probability"):
            if key in system:
                _require(_number(system[key]) and 0 <= float(system[key]) <= 1,
                         f"{prefix}.system.{key} must be within [0, 1]", errors)

        profile = system.get("token_profile", {})
        _require(isinstance(profile, dict), f"{prefix}.system.token_profile must be an object", errors)
        if isinstance(profile, dict):
            _require(
                any(_number(profile.get(field)) and float(profile[field]) > 0 for field in TOKEN_FIELDS),
                f"{prefix}.system.token_profile must declare at least one positive token category",
                errors,
            )
            for field in TOKEN_FIELDS:
                if field in profile:
                    _require(_number(profile[field]) and float(profile[field]) >= 0,
                             f"{prefix}.system.token_profile.{field} must be >= 0", errors)

        human = task.get("human", {})
        role_hours = human.get("hours_by_role")
        _require(isinstance(role_hours, dict) and bool(role_hours),
                 f"{prefix}.human.hours_by_role is required and must be non-empty", errors)
        if isinstance(role_hours, dict):
            for role, hours in role_hours.items():
                _require(_number(hours) and float(hours) >= 0,
                         f"{prefix}.human.hours_by_role.{role} must be a number >= 0", errors)

    if ids:
        for task in tasks:
            for dependency in task.get("depends_on", []) or []:
                _require(dependency in ids,
                         f"task {task.get('id')} depends on unknown task {dependency}", errors)
        errors.extend(_validate_acyclic([t for t in tasks if isinstance(t.get("id"), str)]))
    return errors


def _validate_acyclic(tasks: list[dict[str, Any]]) -> list[str]:
    indegree = {task["id"]: 0 for task in tasks}
    children: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for dependency in task.get("depends_on", []) or []:
            if dependency not in indegree:
                continue
            indegree[task["id"]] += 1
            children[dependency].append(task["id"])
    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return [] if visited == len(indegree) else ["task DAG contains a cycle"]


def validate_pricing(registry: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    models = registry.get("models")
    _require(isinstance(models, list) and bool(models), "pricing.models must be a non-empty list", errors)
    if not isinstance(models, list):
        return errors, warnings

    ids: set[str] = set()
    for index, model in enumerate(models):
        prefix = f"models[{index}]"
        model_id = model.get("id")
        _require(isinstance(model_id, str) and bool(model_id), f"{prefix}.id is required", errors)
        if isinstance(model_id, str) and model_id:
            _require(model_id not in ids, f"duplicate pricing model id: {model_id}", errors)
            ids.add(model_id)
        rates = model.get("rates_per_million")
        _require(isinstance(rates, dict), f"{prefix}.rates_per_million is required", errors)
        if isinstance(rates, dict):
            for field in TOKEN_FIELDS:
                value = rates.get(field)
                _require(
                    _number(value) and float(value) >= 0,  # type: ignore[arg-type]  # guarded by _number
                    f"{prefix}.rates_per_million.{field} must be a non-negative number "
                    "(a null placeholder means the rate has not been verified yet)",
                    errors,
                )
        for field in ("effective_date", "verified_at", "source_reference"):
            _require(bool(model.get(field)), f"{prefix}.{field} is required -- rates need dated provenance", errors)
        if model.get("not_for_billing"):
            warnings.append(f"{model_id or prefix}: illustrative rates, not usable for billing")
    return errors, warnings


def validate_all(
    project: dict[str, Any], tasks: dict[str, Any], pricing: dict[str, Any]
) -> tuple[list[str], list[str]]:
    errors = validate_project(project) + validate_tasks(tasks)
    pricing_errors, warnings = validate_pricing(pricing)
    errors.extend(pricing_errors)

    system = project.get("system", {})
    capacity_inputs = ("workers", "worker_availability", "parallel_efficiency",
                       "model_concurrency_factor", "code_conflict_factor")
    if all(_number(system.get(key)) for key in capacity_inputs):
        capacity = max(1.0, float(system["workers"]) * float(system["worker_availability"])
                       * float(system["parallel_efficiency"]) * float(system["model_concurrency_factor"])
                       * float(system["code_conflict_factor"]))
        for task in tasks.get("tasks", []) or []:
            units = (task.get("system", {}) or {}).get("worker_units", 1)
            if _number(units) and float(units) > capacity + 1e-9:
                errors.append(
                    f"task {task.get('id')} declares worker_units={units} but effective capacity is "
                    f"{capacity:.3f}; raise system.workers or split the task"
                )

    roles = set(project.get("human", {}).get("roles", {}) or {})
    for task in tasks.get("tasks", []) or []:
        for role in (task.get("human", {}) or {}).get("hours_by_role", {}) or {}:
            if role not in roles:
                errors.append(
                    f"task {task.get('id')} uses human role '{role}' that project.human.roles does not declare"
                )
    return errors, warnings
