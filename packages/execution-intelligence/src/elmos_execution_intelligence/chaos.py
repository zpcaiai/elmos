"""Skill 17 — chaos and recovery validator.

Injects a fault into a real durable run and asserts the recovery property that
fault is supposed to exercise. Every scenario states its assertions explicitly,
so a scenario that could not run is reported as not-run rather than as a pass.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .durable import DurableStore, LogicalClock, Orchestrator, TaskOutcome, replay_is_gapless
from .runner import render_template, simulated_executor


class InjectedWorkerDeath(BaseException):
    """Simulates a worker vanishing: not an application error, so it is not caught as one."""


def _dag(task_count: int = 4) -> dict[str, Any]:
    tasks = []
    for index in range(task_count):
        tasks.append({
            "id": f"c{index}",
            "name": f"chaos task {index}",
            "depends_on": [f"c{index - 1}"] if index else [],
            "category": "verification",
            "complexity": "medium",
            "system": {
                "optimistic_minutes": 5, "most_likely_minutes": 10, "pessimistic_minutes": 20,
                "worker_units": 1, "failure_probability": 0.0,
                "token_profile": {"input": 1000, "cached_input": 2000, "cache_write": 100,
                                  "output": 300, "reasoning_output": 100},
            },
            "human": {"hours_by_role": {"qa": 1}},
        })
    return {"schema_version": "1.0.0", "dag_id": "chaos-dag", "tasks": tasks}


def _fresh(project: dict[str, Any]) -> tuple[DurableStore, str]:
    store = DurableStore(":memory:", clock=LogicalClock(start=1000.0, step=1.0))
    run_id = store.create_run(project, _dag())
    return store, run_id


def _result(scenario: str, assertions: list[dict[str, Any]], narrative: str,
            checks: dict[str, Any], detection_ms: int, recovery_ms: int,
            residual: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "passed": all(item["ok"] for item in assertions),
        "assertions": assertions,
        "narrative": narrative,
        "reconciliation": checks,
        "detection_ms": detection_ms,
        "recovery_ms": recovery_ms,
        "residual_impact": residual,
    }


def scenario_worker_killed(project: dict[str, Any]) -> dict[str, Any]:
    store, run_id = _fresh(project)
    executor = simulated_executor(seed=7, failure_scale=0.0)

    def dies_on_second(task: dict[str, Any], attempt: int) -> TaskOutcome:
        if task["task_id"] == "c1" and attempt == 1:
            raise InjectedWorkerDeath()
        return executor(task, attempt)

    orchestrator = Orchestrator(store, run_id, capacity=2.0, heartbeat_timeout_seconds=5.0)
    orchestrator.step(dies_on_second)
    try:
        orchestrator.step(dies_on_second)
    except InjectedWorkerDeath:
        pass

    open_before = len(store.open_attempts(run_id))
    store.clock.advance(120)
    recovery = Orchestrator(store, run_id, capacity=2.0, heartbeat_timeout_seconds=5.0).resume()
    final = Orchestrator(store, run_id, capacity=2.0, heartbeat_timeout_seconds=5.0) \
        .run_to_completion(executor)
    attempts = store.connection.execute(
        "SELECT COUNT(*) AS n FROM task_attempt WHERE run_id = ? AND task_id = 'c1'", (run_id,)
    ).fetchone()["n"]

    assertions = [
        {"name": "interrupted attempt stayed open for the sweeper", "ok": open_before == 1,
         "observed": open_before},
        {"name": "lost attempt classified as lost_worker, not failed",
         "ok": "c1" in recovery["lost_attempts"], "observed": recovery["lost_attempts"]},
        {"name": "completed work was not redone",
         "ok": recovery["completed_tasks"] == ["c0"], "observed": recovery["completed_tasks"]},
        {"name": "run reached succeeded after recovery", "ok": final["state"] == "succeeded",
         "observed": final["state"]},
        {"name": "c1 was retried exactly once", "ok": attempts == 2, "observed": attempts},
    ]
    checks = Orchestrator(store, run_id).reconcile_before_retry("c1")
    store.close()
    return _result(
        "worker-killed-mid-task", assertions,
        "第二个任务的 Worker 在执行中消失，未写回任何结论。心跳超时后被判定为 lost_worker，"
        "经四步核对后重试，最终整条 DAG 完成。",
        checks, detection_ms=120_000, recovery_ms=1_000,
        residual="无。c0 未重跑，c1 只重试一次。")


def scenario_orchestrator_restart(project: dict[str, Any]) -> dict[str, Any]:
    store, run_id = _fresh(project)
    executor = simulated_executor(seed=11, failure_scale=0.0)
    executed: list[str] = []

    def counting(task: dict[str, Any], attempt: int) -> TaskOutcome:
        executed.append(task["task_id"])
        return executor(task, attempt)

    Orchestrator(store, run_id, capacity=2.0).step(counting)
    Orchestrator(store, run_id, capacity=2.0).step(counting)
    midpoint = list(executed)

    # A brand new orchestrator object stands in for a restarted process.
    final = Orchestrator(store, run_id, capacity=2.0).run_to_completion(counting)

    assertions = [
        {"name": "no task executed twice across the restart",
         "ok": len(executed) == len(set(executed)), "observed": executed},
        {"name": "work completed before the restart was preserved",
         "ok": midpoint == ["c0", "c1"], "observed": midpoint},
        {"name": "run completed after the restart", "ok": final["state"] == "succeeded",
         "observed": final["state"]},
    ]
    store.close()
    return _result(
        "orchestrator-restart", assertions,
        "编排器进程在两个任务之后重启。新进程只从存储恢复状态，不持有任何内存状态，"
        "因此继续执行剩余任务而没有重跑已完成的部分。",
        {"decision": "n/a", "original_request": "n/a", "original_commit": "n/a", "original_artifact": "n/a"},
        detection_ms=0, recovery_ms=0,
        residual="无。")


def scenario_client_disconnect(project: dict[str, Any]) -> dict[str, Any]:
    store, run_id = _fresh(project)
    executor = simulated_executor(seed=13, failure_scale=0.0)
    orchestrator = Orchestrator(store, run_id, capacity=2.0)

    orchestrator.step(executor)
    seen = store.events_since(run_id, 0, limit=10_000)
    last_seen = seen[-1]["seq"]          # the client disconnects here

    orchestrator.run_to_completion(executor)
    replayed = store.events_since(run_id, last_seen, limit=10_000)
    everything = store.events_since(run_id, 0, limit=10_000)

    assertions = [
        {"name": "replay is gapless from the last seen sequence",
         "ok": replay_is_gapless(replayed, last_seen), "observed": [e["seq"] for e in replayed][:5]},
        {"name": "no already-seen event is redelivered",
         "ok": all(event["seq"] > last_seen for event in replayed), "observed": last_seen},
        {"name": "nothing produced while disconnected was dropped",
         "ok": len(seen) + len(replayed) == len(everything),
         "observed": {"seen": len(seen), "replayed": len(replayed), "total": len(everything)}},
        {"name": "execution continued while the client was gone",
         "ok": len(replayed) > 0, "observed": len(replayed)},
    ]
    store.close()
    return _result(
        "client-disconnect-and-reconnect", assertions,
        "客户端在第一个任务后断开，运行继续。重连时带 Last-Event-ID，服务端回放其错过的全部事件，"
        "序号连续、无重复。",
        {"decision": "n/a", "original_request": "n/a", "original_commit": "n/a", "original_artifact": "n/a"},
        detection_ms=0, recovery_ms=0,
        residual="无。事件流是仅追加的，断连不影响执行。")


def scenario_duplicate_submission(project: dict[str, Any]) -> dict[str, Any]:
    store, run_id = _fresh(project)
    effects: list[str] = []

    def effectful(task: dict[str, Any], attempt: int) -> TaskOutcome:
        effects.append(task["task_id"])
        return TaskOutcome(status="succeeded", tokens={"input": 10}, execution_ms=1000,
                           git_commit=f"sim-{task['task_id']}",
                           artifacts=[("shared.txt", b"identical bytes")], model="sim")

    orchestrator = Orchestrator(store, run_id, capacity=2.0)
    orchestrator.run_to_completion(effectful)
    first_effects = list(effects)
    artifacts_after_first = len(store.artifacts(run_id))

    # A duplicate submission of the same logical work under the same keys.
    replays = []
    for task in store.tasks(run_id):
        status, response = store.begin_idempotent(f"task:{run_id}", task["task_id"],
                                                  {"task_id": task["task_id"]})
        replays.append(status)
    store.publish_artifact(run_id, "shared.txt", b"identical bytes")

    assertions = [
        {"name": "every duplicate submission replayed instead of re-executing",
         "ok": set(replays) == {"replayed"}, "observed": replays},
        {"name": "no additional side effect ran",
         "ok": effects == first_effects, "observed": len(effects)},
        {"name": "republishing identical bytes did not create a new artifact version",
         "ok": len(store.artifacts(run_id)) == artifacts_after_first,
         "observed": len(store.artifacts(run_id))},
    ]
    store.close()
    return _result(
        "duplicate-submission", assertions,
        "同一批工作被重复提交。幂等键命中已完成记录，直接返回原响应；重复发布相同字节的 Artifact "
        "被内容寻址去重，没有产生新版本。",
        {"decision": "adopt_existing_result", "original_request": "completed",
         "original_commit": "present", "original_artifact": "present"},
        detection_ms=0, recovery_ms=0,
        residual="无。副作用只发生一次。")


def scenario_idempotency_key_misuse(project: dict[str, Any]) -> dict[str, Any]:
    from .durable import Conflict

    store, run_id = _fresh(project)
    store.begin_idempotent("payment", "k", {"amount": 100})
    store.complete_idempotent("payment", "k", {"receipt": "r"})

    conflicted = False
    try:
        store.begin_idempotent("payment", "k", {"amount": 999})
    except Conflict:
        conflicted = True

    status, response = store.begin_idempotent("payment", "k", {"amount": 100})
    assertions = [
        {"name": "same key with a different body is refused", "ok": conflicted, "observed": conflicted},
        {"name": "same key with the same body still replays the original response",
         "ok": status == "replayed" and response == {"receipt": "r"}, "observed": [status, response]},
    ]
    store.close()
    return _result(
        "idempotency-key-misuse", assertions,
        "同一个幂等键被配上不同的请求体。服务端拒绝而不是把旧响应发给一个不同的请求——"
        "后者会产生几乎无法排查的错误结果。",
        {"decision": "reject", "original_request": "completed", "original_commit": "n/a",
         "original_artifact": "n/a"},
        detection_ms=0, recovery_ms=0,
        residual="无。冲突请求未被执行。")


SCENARIOS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "worker-killed-mid-task": scenario_worker_killed,
    "orchestrator-restart": scenario_orchestrator_restart,
    "client-disconnect-and-reconnect": scenario_client_disconnect,
    "duplicate-submission": scenario_duplicate_submission,
    "idempotency-key-misuse": scenario_idempotency_key_misuse,
}


def run_chaos(project: dict[str, Any], names: list[str] | None = None) -> dict[str, Any]:
    selected = names or list(SCENARIOS)
    unknown = [name for name in selected if name not in SCENARIOS]
    if unknown:
        raise ValueError(f"unknown chaos scenario(s): {unknown}")

    results = [SCENARIOS[name](project) for name in selected]
    not_run = [name for name in SCENARIOS if name not in selected]
    return {
        "schema_version": "1.0.0",
        "artifact": "chaos-test-report",
        "project_id": project["project_id"],
        "scenarios": results,
        "scenarios_not_run": not_run,
        "passed": all(result["passed"] for result in results) and not not_run,
        "counts": {
            "run": len(results),
            "passed": sum(1 for result in results if result["passed"]),
            "failed": sum(1 for result in results if not result["passed"]),
            "not_run": len(not_run),
        },
        "rule": "A scenario that was not run is reported as not-run. It never counts as a pass.",
    }


def render_recovery_evidence(report: dict[str, Any], template_dir: Path | None = None) -> str:
    sections = ["# RECOVERY_EVIDENCE", "",
                f"- 项目：`{report['project_id']}`",
                f"- 场景：执行 {report['counts']['run']} · 通过 {report['counts']['passed']} · "
                f"失败 {report['counts']['failed']} · 未执行 {report['counts']['not_run']}",
                f"- 总体：{'通过' if report['passed'] else '未通过'}",
                ""]
    if report["scenarios_not_run"]:
        sections += ["## 未执行的场景", ""] + \
            [f"- `{name}`（记为未执行，不记为通过）" for name in report["scenarios_not_run"]] + [""]

    for scenario in report["scenarios"]:
        checks = scenario["reconciliation"]
        assertions = "\n".join(
            f"- {'✅' if item['ok'] else '❌'} {item['name']}：`{item['observed']}`"
            for item in scenario["assertions"])
        sections.append(render_template("INCIDENT_RECOVERY_REPORT.md.tmpl", {
            "run_id": scenario["scenario"],
            "scenario": scenario["scenario"],
            "injected_at": "t0",
            "detection_ms": scenario["detection_ms"],
            "recovery_ms": scenario["recovery_ms"],
            "narrative": scenario["narrative"],
            "check_idempotency": checks.get("original_request", "n/a"),
            "evidence_idempotency": "idempotency_key 表",
            "check_commit": checks.get("original_commit", "n/a"),
            "evidence_commit": "checkpoint.git_commit",
            "check_artifact": checks.get("original_artifact", "n/a"),
            "evidence_artifact": "artifact (run, logical_name, sha256)",
            "failure_class": checks.get("decision", "n/a"),
            "evidence_failure_class": "task_attempt.failure_class",
            "assertions": assertions,
            "residual_impact": scenario["residual_impact"],
        }, template_dir))
        sections.append("")
    return "\n".join(sections)
