"""Top-level Temporal workflow definitions for sandbox import and replay."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .models import digest_of
    from .orchestration import _validate_temporal_plan_payload


RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
    non_retryable_error_types=["ContractViolation", "PolicyDenied"],
)


@workflow.defn(name="ElmosChildAgentWorkflow")
class ElmosChildAgentWorkflow:
    def __init__(self) -> None:
        self.cancel_requested = False

    @workflow.signal(name="request_cancel")
    async def request_cancel(self, payload: Mapping[str, Any]) -> None:
        self.cancel_requested = True

    @workflow.run
    async def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.cancel_requested:
            return {"status": "cancelled"}
        value = await workflow.execute_activity(
            "RunChildAgentActivity",
            payload,
            start_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RETRY_POLICY,
        )
        if not isinstance(value, Mapping):
            raise TypeError("child activity returned a non-object")
        return dict(value)


@workflow.defn(name="ElmosTaskWorkflow")
class ElmosTaskWorkflow:
    def __init__(self) -> None:
        self.plan: dict[str, Any] = {}
        self.plan_version = 0
        self.cancel_requested = False
        self.cancel_reason: dict[str, str] | None = None
        self.phase = "created"
        self.running_nodes: set[str] = set()
        self.completed_nodes: set[str] = set()
        self.cancel_requests: dict[str, tuple[str, str]] = {}
        self.start_identity: dict[str, Any] = {}
        self.start_plan_digest = ""
        self.start_manifest_digest = ""
        self.start_idempotency_key = ""

    @workflow.update(name="amend_plan")
    async def amend_plan(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if int(payload["expected_version"]) != self.plan_version:
            raise RuntimeError("plan version conflict")
        if not str(payload.get("actor", "")).strip():
            raise RuntimeError("plan amendment actor is required")
        plan = _validate_temporal_plan_payload(payload["plan"])
        if int(plan["version"]) != self.plan_version + 1:
            raise RuntimeError("plan amendment is not monotonic")
        if dict(plan["identity"]) != dict(self.plan.get("identity", {})):
            raise RuntimeError("plan amendment cannot change workflow identity")
        current = {str(node["node_id"]): dict(node) for node in self.plan.get("nodes", ())}
        incoming = {str(node["node_id"]): dict(node) for node in plan["nodes"]}
        for node_id in self.running_nodes | self.completed_nodes:
            if node_id not in incoming or digest_of(incoming[node_id]) != digest_of(current[node_id]):
                raise RuntimeError("plan amendment cannot remove or mutate running/completed nodes")
        self.plan, self.plan_version = plan, int(plan["version"])
        return {
            "status": "applied",
            "version": self.plan_version,
            "digest": self.plan["digest"],
        }

    @workflow.signal(name="request_cancel")
    async def request_cancel(self, payload: Mapping[str, Any]) -> None:
        actor = str(payload.get("actor", ""))
        reason = str(payload.get("reason", ""))
        idempotency_key = str(payload.get("idempotency_key", ""))
        if not actor or not reason or not idempotency_key:
            raise RuntimeError("cancellation actor and reason are required")
        prior = self.cancel_requests.get(idempotency_key)
        if prior is not None:
            if prior != (actor, reason):
                raise RuntimeError("cancellation idempotency key was reused with different content")
            return
        self.cancel_requests[idempotency_key] = (actor, reason)
        self.cancel_requested = True
        self.cancel_reason = {"actor": actor, "reason": reason}

    @workflow.query(name="runtime_status")
    def runtime_status(self) -> Mapping[str, Any]:
        return {
            "phase": self.phase,
            "plan_version": self.plan_version,
            "cancel_requested": self.cancel_requested,
            "running_nodes": sorted(self.running_nodes),
            "completed_nodes": sorted(self.completed_nodes),
            "identity": self.start_identity,
            "plan_digest": self.start_plan_digest,
            "manifest_digest": self.start_manifest_digest,
            "start_idempotency_key": self.start_idempotency_key,
        }

    @workflow.run
    async def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.plan = _validate_temporal_plan_payload(payload["plan"])
        self.plan_version = int(self.plan["version"])
        self.start_identity = dict(self.plan["identity"])
        self.start_plan_digest = str(self.plan["digest"])
        self.start_manifest_digest = str(payload.get("manifest_digest", ""))
        self.start_idempotency_key = str(payload.get("idempotency_key", ""))
        if not self.start_manifest_digest.startswith("sha256:") or not self.start_idempotency_key:
            raise RuntimeError("Temporal workflow start contract is incomplete")
        workspace, completed = await self._restore_or_bootstrap(payload)
        self.completed_nodes = set(completed)
        pending: dict[str, dict[str, Any]] = {}
        materialized_version = 0
        continuation_start = len(completed)
        self.phase = "children"
        while not self.cancel_requested:
            if materialized_version != self.plan_version:
                current = {str(node["node_id"]): dict(node) for node in self.plan["nodes"]}
                if not self.completed_nodes.issubset(current):
                    raise RuntimeError("active plan removed completed nodes")
                pending = {
                    node_id: node for node_id, node in current.items() if node_id not in self.completed_nodes
                }
                materialized_version = self.plan_version
            if not pending:
                break
            ready = [
                node
                for node in pending.values()
                if all(dependency in completed for dependency in node.get("dependencies", []))
            ]
            if not ready:
                raise RuntimeError("DAG made no progress")
            self.running_nodes = {str(node["node_id"]) for node in ready}
            try:
                results = await asyncio.gather(
                    *[
                        workflow.execute_child_workflow(
                            ElmosChildAgentWorkflow.run,
                            {
                                "parent": {**dict(payload), "plan": self.plan},
                                "node": node,
                                "workspace": workspace,
                            },
                            id=(f"{workflow.info().workflow_id}:{node['node_id']}:v{self.plan_version}"),
                            task_queue=workflow.info().task_queue,
                            cancellation_type=(
                                workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED
                            ),
                        )
                        for node in ready
                    ]
                )
            except Exception as error:  # noqa: BLE001 - every child failure must compensate
                return await self._failed(payload, completed, error)
            self.running_nodes.clear()
            for node, result in zip(ready, results):
                if result.get("status") != "succeeded":
                    self.phase = "compensating"
                    compensation = await workflow.execute_activity(
                        "CompensateTaskActivity",
                        {
                            "payload": payload,
                            "completed": completed,
                            "failed_node": node["node_id"],
                        },
                        start_to_close_timeout=timedelta(minutes=30),
                        retry_policy=RETRY_POLICY,
                    )
                    return {
                        "status": "failed",
                        "completed": completed,
                        "failed_node": node["node_id"],
                        "compensation": compensation,
                    }
                node_id = str(node["node_id"])
                completed[node_id] = result
                self.completed_nodes.add(node_id)
                pending.pop(node_id, None)
            if pending and len(completed) - continuation_start >= 100:
                workflow.continue_as_new(
                    {
                        **dict(payload),
                        "plan": self.plan,
                        "resume_state": {"workspace": workspace, "completed": completed},
                    }
                )
        if self.cancel_requested:
            self.phase = "cancelled"
            compensation = await workflow.execute_activity(
                "CompensateTaskActivity",
                {"payload": payload, "completed": completed, "cancel": self.cancel_reason},
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RETRY_POLICY,
            )
            return {
                "status": "cancelled",
                "completed": completed,
                "compensation": compensation,
            }
        return await self._integrate(payload, completed)

    async def _restore_or_bootstrap(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[Any, dict[str, Mapping[str, Any]]]:
        resume_state = payload.get("resume_state")
        if resume_state is None:
            self.phase = "bootstrap"
            workspace = await workflow.execute_activity(
                "BootstrapWorkspaceActivity",
                payload,
                start_to_close_timeout=timedelta(minutes=15),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RETRY_POLICY,
            )
            await workflow.execute_activity(
                "BuildRepoIntelligenceActivity",
                {**dict(payload), "workspace": workspace},
                start_to_close_timeout=timedelta(minutes=30),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RETRY_POLICY,
            )
            return workspace, {}
        if (
            not isinstance(resume_state, Mapping)
            or "workspace" not in resume_state
            or not isinstance(resume_state.get("completed"), Mapping)
        ):
            raise RuntimeError("Temporal continuation state is invalid")
        completed: dict[str, Mapping[str, Any]] = {}
        for node_id, result in dict(resume_state["completed"]).items():
            if not isinstance(result, Mapping):
                raise TypeError("Temporal continuation contains an invalid child result")
            completed[str(node_id)] = dict(result)
        planned = {str(node["node_id"]) for node in self.plan["nodes"]}
        if not set(completed).issubset(planned):
            raise RuntimeError("Temporal continuation references nodes absent from the active plan")
        return resume_state["workspace"], completed

    async def _failed(
        self,
        payload: Mapping[str, Any],
        completed: Mapping[str, Mapping[str, Any]],
        error: Exception,
    ) -> Mapping[str, Any]:
        self.running_nodes.clear()
        self.phase = "compensating"
        compensation = await workflow.execute_activity(
            "CompensateTaskActivity",
            {
                "payload": payload,
                "completed": completed,
                "failure_type": type(error).__name__,
            },
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RETRY_POLICY,
        )
        return {
            "status": "failed",
            "completed": completed,
            "failure_type": type(error).__name__,
            "compensation": compensation,
        }

    async def _integrate(
        self,
        payload: Mapping[str, Any],
        completed: Mapping[str, Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        try:
            self.phase = "integration"
            integrated = await workflow.execute_activity(
                "IntegrateResultsActivity",
                {"payload": payload, "completed": completed},
                start_to_close_timeout=timedelta(hours=1),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RETRY_POLICY,
            )
            self.phase = "verification"
            verified = await workflow.execute_activity(
                "VerifyTaskActivity",
                {"payload": payload, "integrated": integrated},
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RETRY_POLICY,
            )
            self.phase = "finalizing"
            result = await workflow.execute_activity(
                "FinalizeEvidenceActivity",
                {"payload": payload, "integrated": integrated, "verified": verified},
                start_to_close_timeout=timedelta(minutes=30),
                retry_policy=RETRY_POLICY,
            )
        except Exception as error:  # noqa: BLE001 - every integration failure must compensate
            return await self._failed(payload, completed, error)
        self.phase = "completed"
        if not isinstance(result, Mapping):
            raise TypeError("evidence finalization returned a non-object")
        return dict(result)
