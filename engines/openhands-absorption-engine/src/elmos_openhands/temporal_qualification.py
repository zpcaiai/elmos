"""Real Temporal worker-replacement and history-replay qualification."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from .models import Identity, digest_of
from .orchestration import (
    ChildAgentContract,
    DagPlan,
    TemporalClient,
    TemporalDagOrchestrator,
    WorkspaceStrategy,
    build_temporal_workflow_definitions,
)
from .qualification_probes import ProbeResult


def build_temporal_qualification_activities(
    marker_path: str | Path,
    *,
    stall_once: bool,
) -> tuple[Callable[..., Any], ...]:
    """Build the exact named activities consumed by the production workflow."""

    from temporalio import activity

    marker = Path(marker_path)

    @activity.defn(name="BootstrapWorkspaceActivity")
    async def bootstrap(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        activity.heartbeat("bootstrap")
        return {
            "workspace_id": "qualification-workspace",
            "manifest_digest": str(payload["manifest_digest"]),
        }

    @activity.defn(name="BuildRepoIntelligenceActivity")
    async def intelligence(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        activity.heartbeat("intelligence")
        return {"status": "indexed", "workspace": payload["workspace"]}

    @activity.defn(name="RunChildAgentActivity")
    async def child(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        node = payload["node"]
        node_id = str(node["node_id"])
        info = activity.info()
        if stall_once and node_id == "analyze" and not marker.exists():
            marker.write_text(
                str(info.attempt),
                encoding="utf-8",
            )
            while True:
                activity.heartbeat({"node_id": node_id, "attempt": info.attempt})
                await asyncio.sleep(1)
        activity.heartbeat({"node_id": node_id, "attempt": info.attempt})
        return {
            "status": "succeeded",
            "node_id": node_id,
            "attempt": info.attempt,
            "output_digest": digest_of({"node": node_id, "task": node["task"]}),
        }

    @activity.defn(name="IntegrateResultsActivity")
    async def integrate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        activity.heartbeat("integrate")
        completed = payload["completed"]
        return {
            "status": "integrated",
            "nodes": sorted(completed),
            "digest": digest_of(completed),
        }

    @activity.defn(name="VerifyTaskActivity")
    async def verify(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        activity.heartbeat("verify")
        return {"status": "verified", "integration_digest": payload["integrated"]["digest"]}

    @activity.defn(name="FinalizeEvidenceActivity")
    async def finalize(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "succeeded",
            "evidence_digest": digest_of(
                {
                    "integrated": payload["integrated"],
                    "verified": payload["verified"],
                }
            ),
        }

    @activity.defn(name="CompensateTaskActivity")
    async def compensate(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"status": "compensated", "digest": digest_of(payload)}

    return bootstrap, intelligence, child, integrate, verify, finalize, compensate


async def run_temporal_worker(
    address: str,
    task_queue: str,
    marker_path: str | Path,
    *,
    stall_once: bool,
) -> None:
    from temporalio.client import Client
    from temporalio.worker import Worker

    client = await Client.connect(address)
    task_workflow, child_workflow = build_temporal_workflow_definitions()
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=(task_workflow, child_workflow),
        activities=build_temporal_qualification_activities(marker_path, stall_once=stall_once),
    )
    await worker.run()


async def run_temporal_probe(
    *,
    address: str,
    worker_command: Sequence[str],
    evidence_root: str | Path,
) -> ProbeResult:
    """Kill a worker mid-activity, replace it, then replay the exact history."""

    from temporalio.api.enums.v1 import EventType
    from temporalio.client import Client
    from temporalio.worker import Replayer

    if not worker_command or not Path(worker_command[0]).is_absolute():
        raise ValueError("Temporal worker command must use an absolute executable")
    root = Path(evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex
    marker = root / ("worker-started-" + suffix)
    queue = "elmos-oh-qualification-" + suffix
    common = [*worker_command, "worker", "--address", address, "--task-queue", queue, "--marker", str(marker)]
    first = _start_worker([*common, "--stall-once"])
    second: subprocess.Popen[bytes] | None = None
    started = time.monotonic()
    try:
        await asyncio.sleep(1.5)
        client = await Client.connect(address)
        identity = Identity("qualification-a", "project-a", "task-temporal", "temporal-" + suffix)
        nodes = (
            ChildAgentContract(
                "analyze",
                "produce an immutable source inventory",
                ("sha256:" + "a" * 64,),
                {"type": "object"},
                workspace_strategy=WorkspaceStrategy.SHARED_READ_ONLY,
            ),
            ChildAgentContract(
                "verify",
                "verify the source inventory",
                ("sha256:" + "b" * 64,),
                {"type": "object"},
                dependencies=("analyze",),
                workspace_strategy=WorkspaceStrategy.SHARED_READ_ONLY,
            ),
        )
        plan = DagPlan.create(identity, 1, nodes, "real Temporal qualification")
        manifest = "sha256:" + hashlib.sha256(("temporal:" + suffix).encode()).hexdigest()
        idempotency_key = "temporal-start-" + suffix
        orchestrator = TemporalDagOrchestrator(cast(TemporalClient, client), task_queue=queue)
        temporal_start = await orchestrator.start(
            plan,
            manifest_digest=manifest,
            idempotency_key=idempotency_key,
        )
        await _wait_for_path(marker, timeout=30)
        first.kill()
        await asyncio.to_thread(first.wait, 10)
        second = _start_worker(common)
        handle = client.get_workflow_handle(temporal_start.workflow_id)
        result = await asyncio.wait_for(handle.result(), timeout=120)
        if not isinstance(result, Mapping) or result.get("status") != "succeeded":
            raise AssertionError("Temporal workflow did not complete successfully after worker replacement")
        duplicate = await orchestrator.start(
            plan,
            manifest_digest=manifest,
            idempotency_key=idempotency_key,
        )
        if duplicate.workflow_id != temporal_start.workflow_id:
            raise AssertionError("Temporal duplicate start changed workflow identity")
        history = await handle.fetch_history()
        child_handle = client.get_workflow_handle(temporal_start.workflow_id + ":analyze:v1")
        child_history = await child_handle.fetch_history()
        task_workflow, child_workflow = build_temporal_workflow_definitions()
        replayer = Replayer(workflows=(task_workflow, child_workflow))
        parent_replay = await replayer.replay_workflow(history)
        child_replay = await replayer.replay_workflow(child_history)
        if parent_replay.replay_failure is not None:
            raise parent_replay.replay_failure
        if child_replay.replay_failure is not None:
            raise child_replay.replay_failure
        history_json = canonical_temporal_history(history.to_json(), child_history.to_json())
        history_path = root / ("history-" + suffix + ".json")
        history_path.write_text(history_json, encoding="utf-8")
        activity_attempts = [
            event.activity_task_started_event_attributes.attempt
            for event in child_history.events
            if EventType.Name(event.event_type) == "EVENT_TYPE_ACTIVITY_TASK_STARTED"
        ]
        max_activity_attempt = max(activity_attempts, default=0)
        if max_activity_attempt < 2:
            raise AssertionError("Temporal child history does not show worker-death activity retry")
        return ProbeResult(
            "temporal-real",
            "PASS",
            {
                "history_events": len(history.events) + len(child_history.events),
                "max_activity_attempt": max_activity_attempt,
                "worker_replacements": 1,
                "history_replays": 1,
                "duration_seconds": round(time.monotonic() - started, 3),
            },
            (
                "LOCAL_TEMPORAL_POSTGRES_SELF_ATTESTED",
                "TEMPORAL_MULTI_NODE_FAILOVER_NOT_RUN",
                "INDEPENDENT_VERIFICATION_NOT_RUN",
            ),
            {
                "workflow_id": temporal_start.workflow_id,
                "run_id_digest": digest_of(temporal_start.run_id),
                "plan_digest": plan.digest,
                "result": dict(result),
                "activity_attempts": activity_attempts,
                "history_digest": "sha256:" + hashlib.sha256(history_json.encode()).hexdigest(),
                "history_path": str(history_path),
                "first_worker_exit_code": first.returncode,
            },
        )
    finally:
        _stop_worker(first)
        if second is not None:
            _stop_worker(second)


def _start_worker(command: Sequence[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def canonical_temporal_history(parent: str, child: str) -> str:
    import json

    return json.dumps(
        {"parent": json.loads(parent), "analyze_child": json.loads(child)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _stop_worker(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


async def _wait_for_path(path: Path, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError("Temporal qualification activity did not start")
