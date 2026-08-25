"""Wiring between the estimator and the durable orchestrator.

`simulated_executor` turns a task's own estimate into a synthetic execution:
sampled duration, sampled tokens, occasional failures drawn from the task's own
`failure_probability`. It is a harness, not a claim about real work -- but it
produces real telemetry rows, real checkpoints and a real event stream, which is
what makes the durable properties testable and the calibrate loop closeable
before any agent worker exists.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .durable import DurableStore, Orchestrator, TaskOutcome
from .io_utils import markdown_table
from .resource_paths import TEMPLATE_DIR
from .simulation import TOKEN_FIELDS, effective_capacity


def render_template(name: str, values: dict[str, Any], template_dir: Path | None = None) -> str:
    """Fill a `{{placeholder}}` template. Unfilled placeholders are an error, not a blank."""
    path = (template_dir or TEMPLATE_DIR) / name
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    import re

    leftover = sorted(set(re.findall(r"\{\{(\w+)\}\}", text)))
    if leftover:
        raise ValueError(f"template {name} has unfilled placeholders: {leftover}")
    return text


def execution_waves(task_document: dict[str, Any]) -> list[list[str]]:
    """Group tasks into dependency waves. Wave N can only start once N-1 is done."""
    tasks = {task["id"]: task for task in task_document["tasks"]}
    placed: dict[str, int] = {}
    remaining = set(tasks)
    wave_index = 0
    waves: list[list[str]] = []
    while remaining:
        wave = sorted(
            task_id for task_id in remaining
            if all(dep in placed for dep in tasks[task_id].get("depends_on", []) if dep in tasks)
        )
        if not wave:
            raise ValueError("Task DAG contains a cycle")
        for task_id in wave:
            placed[task_id] = wave_index
        remaining -= set(wave)
        waves.append(wave)
        wave_index += 1
    return waves


def render_execution_plan(project: dict[str, Any], task_document: dict[str, Any],
                          run_id: str, generated_at: str,
                          template_dir: Path | None = None) -> str:
    from .decompose import critical_path_seed

    tasks = {task["id"]: task for task in task_document["tasks"]}
    waves = execution_waves(task_document)
    capacity = effective_capacity(project["system"])
    seed = critical_path_seed(task_document)

    wave_rows = [
        [index + 1, len(wave), ", ".join(wave),
         round(sum(float(tasks[t]["system"]["worker_units"]) for t in wave), 2)]
        for index, wave in enumerate(waves)
    ]
    recovery_rows = [
        [task["id"],
         task["system"].get("failure_probability", 0),
         "{}/{}/{}".format(task["system"].get("recovery_optimistic_minutes", 0),
                           task["system"].get("recovery_most_likely_minutes", 0),
                           task["system"].get("recovery_pessimistic_minutes", 0)),
         task["system"].get("rework_probability", 0)]
        for task in task_document["tasks"]
    ]
    return render_template("TASK_EXECUTION_PLAN.md.tmpl", {
        "project_id": project["project_id"],
        "run_id": run_id,
        "dag_id": task_document.get("dag_id", "dag"),
        "task_count": len(tasks),
        "effective_capacity": round(capacity, 3),
        "configured_workers": project["system"]["workers"],
        "dod_level": project["definition_of_done"]["level"],
        "generated_at": generated_at,
        "wave_table": markdown_table(["波次", "任务数", "任务", "并发 worker units"], wave_rows),
        "critical_path": " → ".join(seed["critical_path"]),
        "critical_path_minutes": seed["critical_path_minutes"],
        "recovery_table": markdown_table(
            ["任务", "失败概率", "恢复分钟 乐观/最可能/悲观", "返工概率"], recovery_rows),
        "excludes": "\n".join(
            f"- {item}" for item in (
                "人工审批", "人工验收与复核", "凭据与访问开通等待", "外部业务或供应商决策")),
    }, template_dir)


def simulated_executor(
    seed: int = 42, failure_scale: float = 1.0,
    duration_jitter: tuple[float, float] = (0.7, 1.6),
) -> Callable[[dict[str, Any], int], TaskOutcome]:
    """Build a deterministic synthetic executor from each task's own estimate."""
    rng = random.Random(  # noqa: S311 - Monte Carlo, not cryptography; seeded on purpose
        seed)

    def execute(task: dict[str, Any], attempt: int) -> TaskOutcome:
        estimate = task["estimate"] if "estimate" in task else task.get("system", {})
        minutes = float(estimate.get("most_likely_minutes", 1.0)) * rng.uniform(*duration_jitter)
        profile = estimate.get("token_profile", {})
        tokens = {
            field: int(float(profile.get(field, 0)) * rng.uniform(0.8, 1.5))
            for field in TOKEN_FIELDS
        }
        failure_probability = float(estimate.get("failure_probability", 0.0)) * failure_scale
        if attempt <= 2 and rng.random() < failure_probability:
            return TaskOutcome(status="failed", failure_class="transient",
                               tokens=tokens, execution_ms=int(minutes * 60_000 * 0.4),
                               model="simulated")
        return TaskOutcome(
            status="succeeded",
            tokens=tokens,
            execution_ms=int(minutes * 60_000),
            git_commit=f"sim-{task['task_id']}-{attempt}",
            artifacts=[(f"{task['task_id']}.result", f"{task['task_id']}:{attempt}".encode())],
            model="simulated",
        )

    return execute


def execute_run(project: dict[str, Any], task_document: dict[str, Any], store: DurableStore,
                capacity: float | None = None, seed: int = 42,
                failure_scale: float = 1.0, worker_id: str = "sim-worker") -> dict[str, Any]:
    run_id = store.create_run(project, task_document)
    orchestrator = Orchestrator(
        store, run_id,
        capacity=capacity if capacity is not None else effective_capacity(project["system"]),
        worker_id=worker_id,
    )
    result = orchestrator.run_to_completion(simulated_executor(seed=seed, failure_scale=failure_scale))
    return {"run_id": run_id, **result}
