"""Typed atomic-task and deterministic DAG validation."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .contracts import (
    ContractError,
    normalize_relative_path,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .models import TaskRisk


@dataclass(frozen=True, slots=True)
class AtomicTask:
    task_id: str
    title: str
    objective: str
    task_class: str
    owned_paths: tuple[str, ...]
    read_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    dependencies: tuple[str, ...]
    acceptance: tuple[str, ...]
    risk: TaskRisk
    complexity: Mapping[str, Any]
    lifecycle_status: str
    read_only: bool = False

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AtomicTask":
        value = require_mapping(payload, "task")
        allowed = {
            "id",
            "title",
            "objective",
            "task_class",
            "owned_paths",
            "read_paths",
            "forbidden_paths",
            "dependencies",
            "acceptance",
            "risk",
            "complexity",
            "status",
            "read_only",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            enriched = sorted(set(unknown) & {"context_pack", "routing"})
            code = "enriched_task_not_atomic_planning_input" if enriched else "unknown_task_field"
            raise ContractError(code, "unknown atomic-planning task field(s): " + ", ".join(unknown))
        task_id = require_string(value.get("id"), "task.id")
        read_only = value.get("read_only", False)
        if not isinstance(read_only, bool):
            raise ContractError("invalid_read_only", f"task {task_id} read_only must be boolean")

        def paths(key: str) -> tuple[str, ...]:
            raw = require_string_sequence(value.get(key, []), f"task.{key}")
            normalized = tuple(normalize_relative_path(item, f"task.{key}[]") for item in raw)
            if len(set(item.casefold() for item in normalized)) != len(normalized):
                raise ContractError("duplicate_path", f"task {task_id} {key} contains duplicate normalized paths")
            return normalized

        owned = paths("owned_paths")
        if not owned and not read_only:
            raise ContractError("missing_owned_paths", f"task {task_id} must own a path or declare read_only")
        acceptance = require_string_sequence(value.get("acceptance", []), "task.acceptance", allow_empty=False)
        dependencies = require_string_sequence(value.get("dependencies", []), "task.dependencies")
        if task_id in dependencies:
            raise ContractError("self_dependency", f"task {task_id} depends on itself")
        lifecycle_status = value.get("status", "planned")
        allowed_statuses = {"planned", "ready", "running", "blocked", "failed", "passed", "waived"}
        if lifecycle_status not in allowed_statuses:
            raise ContractError("invalid_task_status", f"task {task_id} status is not in the closed lifecycle")
        complexity_value = require_mapping(value.get("complexity", {}), "task.complexity")
        complexity_allowed = {"state", "score", "category", "context_tokens"}
        complexity_unknown = sorted(set(complexity_value) - complexity_allowed)
        if complexity_unknown:
            raise ContractError("unknown_complexity_field", "unknown complexity field(s): " + ", ".join(complexity_unknown))
        complexity_state = complexity_value.get("state", "not_run")
        if complexity_state not in {"not_run", "validated"}:
            raise ContractError("invalid_complexity_state", "complexity.state must be not_run or validated")
        complexity: dict[str, Any] = {"state": complexity_state}
        if complexity_state == "validated":
            score = complexity_value.get("score")
            context_tokens = complexity_value.get("context_tokens")
            if isinstance(score, bool) or not isinstance(score, int) or score < 0:
                raise ContractError("invalid_complexity_score", "validated complexity.score must be a non-negative integer")
            if isinstance(context_tokens, bool) or not isinstance(context_tokens, int) or context_tokens < 0:
                raise ContractError("invalid_context_tokens", "validated complexity.context_tokens must be a non-negative integer")
            category = complexity_value.get("category")
            if category not in {"simple", "standard", "complex", "long_horizon"}:
                raise ContractError("invalid_complexity_category", "validated complexity.category is invalid")
            complexity.update({"score": score, "category": category, "context_tokens": context_tokens})
        elif set(complexity_value) - {"state"}:
            raise ContractError("premature_complexity_values", "not_run complexity cannot carry estimated values")
        task = cls(
            task_id=task_id,
            title=require_string(value.get("title"), "task.title"),
            objective=require_string(value.get("objective"), "task.objective"),
            task_class=require_string(value.get("task_class", "standard"), "task.task_class"),
            owned_paths=owned,
            read_paths=paths("read_paths"),
            forbidden_paths=paths("forbidden_paths"),
            dependencies=dependencies,
            acceptance=acceptance,
            risk=TaskRisk.from_payload(value.get("risk")),
            complexity=complexity,
            lifecycle_status=lifecycle_status,
            read_only=read_only,
        )
        for owned_path in task.owned_paths:
            if any(paths_overlap(owned_path, denied) for denied in task.forbidden_paths):
                raise ContractError("owned_forbidden_overlap", f"task {task_id} owns forbidden path {owned_path}")
        for index, left in enumerate(task.owned_paths):
            for right in task.owned_paths[index + 1 :]:
                if paths_overlap(left, right):
                    raise ContractError("self_path_overlap", f"task {task_id} has overlapping ownership: {left}, {right}")
        return task

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "title": self.title,
            "objective": self.objective,
            "task_class": self.task_class,
            "owned_paths": list(self.owned_paths),
            "read_paths": list(self.read_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "dependencies": list(self.dependencies),
            "acceptance": list(self.acceptance),
            "risk": {
                "security": self.risk.security.name.lower(),
                "data_migration": self.risk.data_migration.name.lower(),
                "concurrency": self.risk.concurrency.name.lower(),
                "public_contract": self.risk.public_contract.name.lower(),
                "blast_radius": self.risk.blast_radius.name.lower(),
            },
            "complexity": dict(self.complexity),
            "status": self.lifecycle_status,
            "read_only": self.read_only,
        }


def _has_glob(path: str) -> bool:
    return any(character in path for character in "*?[")


def _fixed_prefix(path: str) -> str:
    parts: list[str] = []
    for part in path.casefold().split("/"):
        if any(character in part for character in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


def _prefix_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def paths_overlap(left: str, right: str) -> bool:
    """Conservatively detect overlap between normalized repository path claims."""

    a = normalize_relative_path(left).casefold().rstrip("/")
    b = normalize_relative_path(right).casefold().rstrip("/")
    a_glob = _has_glob(a)
    b_glob = _has_glob(b)
    if not a_glob and not b_glob:
        return _prefix_overlap(a, b)
    if a_glob and not b_glob and fnmatch.fnmatchcase(b, a):
        return True
    if b_glob and not a_glob and fnmatch.fnmatchcase(a, b):
        return True
    a_prefix = _fixed_prefix(a)
    b_prefix = _fixed_prefix(b)
    if not a_prefix or not b_prefix:
        return True
    return _prefix_overlap(a_prefix, b_prefix)


@dataclass(frozen=True, slots=True)
class DagPlan:
    tasks: Mapping[str, AtomicTask]
    waves: tuple[tuple[str, ...], ...]
    critical_path: tuple[str, ...]
    digest: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "tasks": [self.tasks[key].to_payload() for key in sorted(self.tasks)],
            "waves": [list(wave) for wave in self.waves],
            "critical_path": list(self.critical_path),
            "digest": self.digest,
        }


def _validate_task_set(tasks: Sequence[AtomicTask]) -> dict[str, AtomicTask]:
    by_id: dict[str, AtomicTask] = {}
    for task in tasks:
        if task.task_id in by_id:
            raise ContractError("duplicate_task_id", f"duplicate task id: {task.task_id}")
        by_id[task.task_id] = task
    if not by_id:
        raise ContractError("empty_task_set", "at least one task is required")
    for task in tasks:
        missing = sorted(set(task.dependencies) - set(by_id))
        if missing:
            raise ContractError("missing_dependency", f"task {task.task_id} has missing dependencies: {missing}")
    return by_id


def _topological_order(tasks: Mapping[str, AtomicTask]) -> tuple[str, ...]:
    indegree = {task_id: len(task.dependencies) for task_id, task in tasks.items()}
    dependents: dict[str, list[str]] = {task_id: [] for task_id in tasks}
    for task in tasks.values():
        for dependency in task.dependencies:
            dependents[dependency].append(task.task_id)
    ready = sorted(task_id for task_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        task_id = ready.pop(0)
        order.append(task_id)
        for dependent in sorted(dependents[task_id]):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
                ready.sort()
    if len(order) != len(tasks):
        cycle_nodes = sorted(task_id for task_id, degree in indegree.items() if degree > 0)
        raise ContractError("dag_cycle", f"task dependency cycle detected: {cycle_nodes}")
    return tuple(order)


def _can_share_wave(candidate: AtomicTask, selected: Iterable[AtomicTask]) -> bool:
    for other in selected:
        for left in candidate.owned_paths:
            for right in other.owned_paths:
                if paths_overlap(left, right):
                    return False
    return True


def _build_waves(tasks: Mapping[str, AtomicTask]) -> tuple[tuple[str, ...], ...]:
    remaining = set(tasks)
    completed: set[str] = set()
    waves: list[tuple[str, ...]] = []
    while remaining:
        ready = sorted(task_id for task_id in remaining if set(tasks[task_id].dependencies) <= completed)
        if not ready:
            raise ContractError("dag_cycle", "no runnable task remains")
        selected: list[AtomicTask] = []
        for task_id in ready:
            candidate = tasks[task_id]
            if _can_share_wave(candidate, selected):
                selected.append(candidate)
        wave = tuple(task.task_id for task in selected)
        waves.append(wave)
        completed.update(wave)
        remaining.difference_update(wave)
    return tuple(waves)


def _critical_path(tasks: Mapping[str, AtomicTask], order: Sequence[str]) -> tuple[str, ...]:
    best: dict[str, tuple[str, ...]] = {}
    for task_id in order:
        dependencies = tasks[task_id].dependencies
        if not dependencies:
            best[task_id] = (task_id,)
            continue
        candidates = [best[dependency] + (task_id,) for dependency in dependencies]
        longest = max(len(path) for path in candidates)
        best[task_id] = min(path for path in candidates if len(path) == longest)
    maximum = max(len(path) for path in best.values())
    return min(path for path in best.values() if len(path) == maximum)


def build_dag(task_payloads: Sequence[Mapping[str, Any]]) -> DagPlan:
    if not isinstance(task_payloads, Sequence) or isinstance(task_payloads, (str, bytes, bytearray)):
        raise ContractError("invalid_tasks", "tasks must be an array")
    tasks = [AtomicTask.from_payload(item) for item in task_payloads]
    by_id = _validate_task_set(tasks)
    order = _topological_order(by_id)
    waves = _build_waves(by_id)
    critical = _critical_path(by_id, order)
    body = {
        "tasks": [by_id[key].to_payload() for key in sorted(by_id)],
        "waves": waves,
        "critical_path": critical,
    }
    return DagPlan(tasks=by_id, waves=waves, critical_path=critical, digest=sha256_payload(body))


def validate_declared_waves(plan: DagPlan, waves: Sequence[Sequence[str]]) -> None:
    if not isinstance(waves, Sequence) or isinstance(waves, (str, bytes, bytearray)) or not waves:
        raise ContractError("invalid_waves", "waves must be a non-empty array")
    seen: set[str] = set()
    completed: set[str] = set()
    for index, raw_wave in enumerate(waves):
        if not isinstance(raw_wave, Sequence) or isinstance(raw_wave, (str, bytes, bytearray)) or not raw_wave:
            raise ContractError("invalid_wave", f"wave {index} must be a non-empty array")
        wave = tuple(raw_wave)
        if any(not isinstance(item, str) for item in wave):
            raise ContractError("invalid_wave", f"wave {index} contains a non-string task id")
        if len(set(wave)) != len(wave):
            raise ContractError("duplicate_wave_task", f"wave {index} contains duplicate task ids")
        unknown = sorted(set(wave) - set(plan.tasks))
        if unknown:
            raise ContractError("unknown_wave_task", f"wave {index} contains unknown tasks: {unknown}")
        repeated = sorted(set(wave) & seen)
        if repeated:
            raise ContractError("duplicate_wave_task", f"tasks appear in multiple waves: {repeated}")
        selected = [plan.tasks[item] for item in wave]
        for task in selected:
            missing = sorted(set(task.dependencies) - completed)
            if missing:
                raise ContractError("wave_dependency_violation", f"task {task.task_id} runs before dependencies: {missing}")
        for left_index, left in enumerate(selected):
            if not _can_share_wave(left, selected[:left_index] + selected[left_index + 1 :]):
                raise ContractError("wave_path_overlap", f"wave {index} has overlapping write ownership")
        seen.update(wave)
        completed.update(wave)
    missing_tasks = sorted(set(plan.tasks) - seen)
    if missing_tasks:
        raise ContractError("missing_wave_task", f"tasks absent from waves: {missing_tasks}")
