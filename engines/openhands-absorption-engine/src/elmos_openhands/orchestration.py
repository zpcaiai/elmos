"""Temporal-backed durable DAG orchestration and compensation semantics."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from .dag import AgentNode, DurableAgentDag
from .errors import BudgetExceeded, ContractViolation, NotConfigured, TenantIsolationError
from .models import Identity, canonical_json, digest_of


class WorkspaceStrategy(StrEnum):
    WORKTREE = "worktree"
    CLONE = "clone"
    SHARED_READ_ONLY = "shared_read_only"


@dataclass(frozen=True, slots=True)
class ChildAgentContract:
    node_id: str
    task: str
    input_refs: tuple[str, ...]
    output_contract: Mapping[str, Any]
    dependencies: tuple[str, ...] = ()
    workspace_strategy: WorkspaceStrategy = WorkspaceStrategy.WORKTREE
    provider_preferences: tuple[str, ...] = ()
    budget_micros: int = 0
    max_attempts: int = 3
    compensation: str | None = None

    def __post_init__(self) -> None:
        if not self.node_id or not self.task.strip() or not self.output_contract:
            raise ContractViolation("child-agent contract is incomplete")
        if self.node_id in self.dependencies or self.budget_micros < 0 or self.max_attempts < 1:
            raise ContractViolation("child-agent dependency/budget/attempt contract is invalid")
        if any(not ref.startswith(("sha256:", "git:", "artifact:")) for ref in self.input_refs):
            raise ContractViolation("child-agent inputs must be immutable references")


@dataclass(frozen=True, slots=True)
class DagPlan:
    identity: Identity
    version: int
    nodes: tuple[ChildAgentContract, ...]
    reason: str
    digest: str

    @classmethod
    def create(
        cls, identity: Identity, version: int, nodes: Iterable[ChildAgentContract], reason: str
    ) -> DagPlan:
        values = tuple(nodes)
        if version < 1 or not values or not reason.strip():
            raise ContractViolation("DAG plan requires version, nodes and reason")
        graph = {node.node_id: node.dependencies for node in values}
        if (
            len(graph) != len(values)
            or any(dependency not in graph for deps in graph.values() for dependency in deps)
            or _cycle(graph)
        ):
            raise ContractViolation("DAG plan has duplicate, absent or cyclic dependencies")
        body = {
            "identity": identity.scope(),
            "version": version,
            "nodes": [_contract_dict(node) for node in values],
            "reason": reason,
        }
        return cls(identity, version, values, reason, digest_of(body))


@dataclass(frozen=True, slots=True)
class TemporalStartResult:
    workflow_id: str
    run_id: str
    plan_digest: str


class TemporalClient(Protocol):
    async def start_workflow(self, workflow: Any, arg: Any, **kwargs: Any) -> Any: ...
    def get_workflow_handle(self, workflow_id: str, *, run_id: str | None = None) -> Any: ...


class TemporalDagOrchestrator:
    """Production Temporal client adapter; no server is started implicitly."""

    def __init__(self, client: TemporalClient, *, task_queue: str, namespace: str = "default") -> None:
        if not task_queue or not namespace:
            raise ContractViolation("Temporal task queue and namespace are required")
        self.client = client
        self.task_queue = task_queue
        self.namespace = namespace

    async def start(
        self, plan: DagPlan, *, manifest_digest: str, idempotency_key: str
    ) -> TemporalStartResult:
        if not manifest_digest.startswith("sha256:") or not idempotency_key:
            raise ContractViolation("Temporal start requires manifest digest and idempotency")
        workflow_id = "elmos:" + ":".join(plan.identity.scope())
        payload = {
            "schema_version": "1.0",
            "identity": _identity_dict(plan.identity),
            "plan": _plan_dict(plan),
            "manifest_digest": manifest_digest,
            "idempotency_key": idempotency_key,
        }
        try:
            handle = await self.client.start_workflow(
                "ElmosTaskWorkflow",
                payload,
                id=workflow_id,
                task_queue=self.task_queue,
                id_reuse_policy=_reject_duplicate_policy(),
                execution_timeout=timedelta(days=7),
                run_timeout=timedelta(days=1),
                task_timeout=timedelta(seconds=10),
                memo={
                    "tenant_id": plan.identity.tenant_id,
                    "project_id": plan.identity.project_id,
                    "plan_digest": plan.digest,
                },
                search_attributes={
                    "TenantId": [plan.identity.tenant_id],
                    "ProjectId": [plan.identity.project_id],
                },
            )
        except Exception as error:
            # Duplicate starts are resolved through the exact workflow handle;
            # unknown failures remain errors and are never treated as success.
            if type(error).__name__ not in {
                "WorkflowAlreadyStartedError",
                "WorkflowExecutionAlreadyStartedError",
            }:
                raise
            existing = self.client.get_workflow_handle(workflow_id)
            if existing is None:
                raise
            status = await existing.query("runtime_status")
            expected = {
                "identity": _identity_dict(plan.identity),
                "plan_digest": plan.digest,
                "manifest_digest": manifest_digest,
                "start_idempotency_key": idempotency_key,
            }
            if not isinstance(status, Mapping) or any(
                status.get(key) != value for key, value in expected.items()
            ):
                raise ContractViolation(
                    "Temporal workflow identity collision or conflicting duplicate start"
                ) from error
            handle = existing
        temporal_run_id = str(
            getattr(handle, "first_execution_run_id", None) or getattr(handle, "run_id", "unknown")
        )
        return TemporalStartResult(workflow_id, temporal_run_id, plan.digest)

    async def amend(
        self, workflow_id: str, plan: DagPlan, *, expected_version: int, actor: str, idempotency_key: str
    ) -> None:
        if plan.version != expected_version + 1 or not actor or not idempotency_key:
            raise ContractViolation("DAG amendment must increment the expected version and identify actor")
        handle = self.client.get_workflow_handle(workflow_id)
        result = await handle.execute_update(
            "amend_plan",
            {
                "expected_version": expected_version,
                "plan": _plan_dict(plan),
                "actor": actor,
                "idempotency_key": idempotency_key,
            },
            id=idempotency_key,
        )
        if (
            not isinstance(result, Mapping)
            or result.get("status") != "applied"
            or int(result.get("version", -1)) != plan.version
        ):
            raise ContractViolation("Temporal rejected or failed to acknowledge the DAG amendment")

    async def cancel(self, workflow_id: str, *, actor: str, reason: str, idempotency_key: str) -> None:
        if not actor or not reason or not idempotency_key:
            raise ContractViolation("Temporal cancellation requires actor and reason")
        handle = self.client.get_workflow_handle(workflow_id)
        await handle.signal(
            "request_cancel", {"actor": actor, "reason": reason, "idempotency_key": idempotency_key}
        )

    async def status(self, workflow_id: str) -> Mapping[str, Any]:
        handle = self.client.get_workflow_handle(workflow_id)
        value = await handle.query("runtime_status")
        if not isinstance(value, Mapping):
            raise ContractViolation("Temporal status query returned an invalid contract")
        return dict(value)


def build_temporal_workflow_definitions() -> tuple[type[Any], type[Any]]:
    """Build native Temporal workflow classes when temporalio is installed.

    The returned classes are registered with a real Temporal worker. Keeping
    imports lazy allows local unit tests to run without pretending Temporal was
    executed.
    """

    try:
        from .temporal_workflows import ElmosChildAgentWorkflow, ElmosTaskWorkflow
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise NotConfigured("temporalio is required for Temporal execution") from error
    return ElmosTaskWorkflow, ElmosChildAgentWorkflow

    try:
        from temporalio import workflow
        from temporalio.common import RetryPolicy
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise NotConfigured("temporalio is required for Temporal execution") from error
    if not callable(getattr(workflow, "update", None)):
        raise NotConfigured("the configured temporalio runtime lacks durable workflow-update support")

    retry = RetryPolicy(
        initial_interval=timedelta(seconds=1),
        maximum_interval=timedelta(seconds=30),
        maximum_attempts=5,
        non_retryable_error_types=["ContractViolation", "PolicyDenied"],
    )

    class LegacyElmosChildAgentWorkflow:
        def __init__(self) -> None:
            self.cancel_requested = False

        @workflow.signal(name="request_cancel")
        async def request_cancel(self, payload: Mapping[str, Any]) -> None:
            self.cancel_requested = True

        async def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            if self.cancel_requested:
                return {"status": "cancelled"}
            value = await workflow.execute_activity(
                "RunChildAgentActivity",
                payload,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=retry,
            )
            if not isinstance(value, Mapping):
                raise TypeError("child activity returned a non-object")
            return dict(value)

    LegacyElmosChildAgentWorkflow.__qualname__ = "LegacyElmosChildAgentWorkflow"
    LegacyElmosChildAgentWorkflow.run.__qualname__ = "LegacyElmosChildAgentWorkflow.run"
    workflow.run(LegacyElmosChildAgentWorkflow.run)
    workflow.defn(name="LegacyElmosChildAgentWorkflow")(LegacyElmosChildAgentWorkflow)

    class LegacyElmosTaskWorkflow:
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
            current_nodes = {str(node["node_id"]): dict(node) for node in self.plan.get("nodes", ())}
            incoming_nodes = {str(node["node_id"]): dict(node) for node in plan["nodes"]}
            for node_id in self.running_nodes | self.completed_nodes:
                if node_id not in incoming_nodes or digest_of(incoming_nodes[node_id]) != digest_of(
                    current_nodes[node_id]
                ):
                    raise RuntimeError("plan amendment cannot remove or mutate running/completed nodes")
            self.plan, self.plan_version = plan, int(plan["version"])
            return {"status": "applied", "version": self.plan_version, "digest": self.plan["digest"]}

        @workflow.signal(name="request_cancel")
        async def request_cancel(self, payload: Mapping[str, Any]) -> None:
            actor, reason = str(payload.get("actor", "")), str(payload.get("reason", ""))
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

        async def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            self.plan = _validate_temporal_plan_payload(payload["plan"])
            self.plan_version = int(self.plan["version"])
            self.start_identity = dict(self.plan["identity"])
            self.start_plan_digest = str(self.plan["digest"])
            self.start_manifest_digest = str(payload.get("manifest_digest", ""))
            self.start_idempotency_key = str(payload.get("idempotency_key", ""))
            if not self.start_manifest_digest.startswith("sha256:") or not self.start_idempotency_key:
                raise RuntimeError("Temporal workflow start contract is incomplete")
            resume_state = payload.get("resume_state")
            if resume_state is None:
                self.phase = "bootstrap"
                workspace = await workflow.execute_activity(
                    "BootstrapWorkspaceActivity",
                    payload,
                    start_to_close_timeout=timedelta(minutes=15),
                    heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
                await workflow.execute_activity(
                    "BuildRepoIntelligenceActivity",
                    {**dict(payload), "workspace": workspace},
                    start_to_close_timeout=timedelta(minutes=30),
                    heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
                completed: dict[str, Mapping[str, Any]] = {}
            else:
                if (
                    not isinstance(resume_state, Mapping)
                    or "workspace" not in resume_state
                    or not isinstance(resume_state.get("completed"), Mapping)
                ):
                    raise RuntimeError("Temporal continuation state is invalid")
                workspace = resume_state["workspace"]
                completed = {}
                for node_id, result in dict(resume_state["completed"]).items():
                    if not isinstance(result, Mapping):
                        raise TypeError("Temporal continuation contains an invalid child result")
                    completed[str(node_id)] = dict(result)
            plan_node_ids = {str(node["node_id"]) for node in self.plan["nodes"]}
            if not set(completed).issubset(plan_node_ids):
                raise RuntimeError("Temporal continuation references nodes absent from the active plan")
            self.completed_nodes = set(completed)
            pending: dict[str, dict[str, Any]] = {}
            materialized_version = 0
            continuation_start = len(completed)
            self.phase = "children"
            while not self.cancel_requested:
                if materialized_version != self.plan_version:
                    current_nodes = {str(node["node_id"]): dict(node) for node in self.plan["nodes"]}
                    if not self.completed_nodes.issubset(current_nodes):
                        raise RuntimeError("active plan removed completed nodes")
                    pending = {
                        node_id: node
                        for node_id, node in current_nodes.items()
                        if node_id not in self.completed_nodes
                    }
                    materialized_version = self.plan_version
                if not pending:
                    break
                ready = [
                    node
                    for node in pending.values()
                    if all(dep in completed for dep in node.get("dependencies", []))
                ]
                if not ready:
                    raise RuntimeError("DAG made no progress")
                self.running_nodes = {str(node["node_id"]) for node in ready}
                try:
                    results = await asyncio.gather(
                        *[
                            workflow.execute_child_workflow(
                                LegacyElmosChildAgentWorkflow.run,
                                {
                                    "parent": {**dict(payload), "plan": self.plan},
                                    "node": node,
                                    "workspace": workspace,
                                },
                                id=f"{workflow.info().workflow_id}:{node['node_id']}:v{self.plan_version}",
                                task_queue=workflow.info().task_queue,
                                cancellation_type=workflow.ChildWorkflowCancellationType.WAIT_CANCELLATION_COMPLETED,
                            )
                            for node in ready
                        ]
                    )
                except Exception as error:  # noqa: BLE001 - workflow must compensate every child failure
                    self.running_nodes.clear()
                    self.phase = "compensating"
                    compensation = await workflow.execute_activity(
                        "CompensateTaskActivity",
                        {"payload": payload, "completed": completed, "failure_type": type(error).__name__},
                        start_to_close_timeout=timedelta(minutes=30),
                        retry_policy=retry,
                    )
                    return {
                        "status": "failed",
                        "completed": completed,
                        "failure_type": type(error).__name__,
                        "compensation": compensation,
                    }
                self.running_nodes.clear()
                for node, result in zip(ready, results):
                    if result.get("status") != "succeeded":
                        self.phase = "compensating"
                        compensation = await workflow.execute_activity(
                            "CompensateTaskActivity",
                            {"payload": payload, "completed": completed, "failed_node": node["node_id"]},
                            start_to_close_timeout=timedelta(minutes=30),
                            retry_policy=retry,
                        )
                        return {
                            "status": "failed",
                            "completed": completed,
                            "failed_node": node["node_id"],
                            "compensation": compensation,
                        }
                    completed[str(node["node_id"])] = result
                    self.completed_nodes.add(str(node["node_id"]))
                    pending.pop(str(node["node_id"]), None)
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
                    retry_policy=retry,
                )
                return {"status": "cancelled", "completed": completed, "compensation": compensation}
            try:
                self.phase = "integration"
                integrated = await workflow.execute_activity(
                    "IntegrateResultsActivity",
                    {"payload": payload, "completed": completed},
                    start_to_close_timeout=timedelta(hours=1),
                    heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
                self.phase = "verification"
                verified = await workflow.execute_activity(
                    "VerifyTaskActivity",
                    {"payload": payload, "integrated": integrated},
                    start_to_close_timeout=timedelta(hours=2),
                    heartbeat_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
                self.phase = "finalizing"
                result = await workflow.execute_activity(
                    "FinalizeEvidenceActivity",
                    {"payload": payload, "integrated": integrated, "verified": verified},
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=retry,
                )
            except Exception as error:  # noqa: BLE001 - workflow must compensate every integration failure
                self.phase = "compensating"
                compensation = await workflow.execute_activity(
                    "CompensateTaskActivity",
                    {"payload": payload, "completed": completed, "failure_type": type(error).__name__},
                    start_to_close_timeout=timedelta(minutes=30),
                    retry_policy=retry,
                )
                return {
                    "status": "failed",
                    "completed": completed,
                    "failure_type": type(error).__name__,
                    "compensation": compensation,
                }
            self.phase = "completed"
            if not isinstance(result, Mapping):
                raise TypeError("evidence finalization returned a non-object")
            return dict(result)

    LegacyElmosTaskWorkflow.__qualname__ = "LegacyElmosTaskWorkflow"
    LegacyElmosTaskWorkflow.run.__qualname__ = "LegacyElmosTaskWorkflow.run"
    workflow.run(LegacyElmosTaskWorkflow.run)
    workflow.defn(name="LegacyElmosTaskWorkflow")(LegacyElmosTaskWorkflow)
    return LegacyElmosTaskWorkflow, LegacyElmosChildAgentWorkflow


def _reject_duplicate_policy() -> Any:
    """Return the native SDK enum without making Temporal a base dependency."""

    try:
        from temporalio.common import WorkflowIDReusePolicy
    except ImportError:  # pragma: no cover - exercised by dependency-free unit tests
        return "REJECT_DUPLICATE"
    return WorkflowIDReusePolicy.REJECT_DUPLICATE


class DagControlStore:
    """Persists plan versions, budget reservations and compensation receipts."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS dag_plans(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,version INTEGER NOT NULL,digest TEXT NOT NULL,body TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,PRIMARY KEY(tenant_id,run_id,scope_node_id,version));
               CREATE TABLE IF NOT EXISTS dag_budget(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,node_id TEXT NOT NULL,reserved_micros INTEGER NOT NULL,used_micros INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,run_id,scope_node_id,node_id));
               CREATE TABLE IF NOT EXISTS dag_budget_mutations(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,node_id TEXT NOT NULL,cost_micros INTEGER NOT NULL,global_limit_micros INTEGER NOT NULL,PRIMARY KEY(tenant_id,run_id,scope_node_id,idempotency_key));
               CREATE TABLE IF NOT EXISTS dag_compensations(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,node_id TEXT NOT NULL,sequence INTEGER NOT NULL,operation TEXT NOT NULL,idempotency_key TEXT NOT NULL,state TEXT NOT NULL,receipt TEXT,PRIMARY KEY(tenant_id,run_id,scope_node_id,node_id,sequence),UNIQUE(tenant_id,run_id,scope_node_id,idempotency_key));
               CREATE TABLE IF NOT EXISTS workspace_locks(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,scope_node_id TEXT NOT NULL,resource TEXT NOT NULL,owner_node TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,run_id,scope_node_id,resource));"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    def save_plan(self, plan: DagPlan, *, actor: str) -> None:
        if not actor:
            raise ContractViolation("plan actor is required")
        with self._transaction():
            self._assert_run_scope(plan.identity)
            existing = self._connection.execute(
                "SELECT digest,body,actor,reason FROM dag_plans WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND version=?",
                (*plan.identity.scope(), plan.version),
            ).fetchone()
            encoded = canonical_json(_plan_dict(plan))
            if existing is not None:
                if (existing["digest"], existing["body"], existing["actor"], existing["reason"]) == (
                    plan.digest,
                    encoded,
                    actor,
                    plan.reason,
                ):
                    return
                raise ContractViolation("DAG plan version is immutable")
            previous = self._connection.execute(
                "SELECT MAX(version) FROM dag_plans WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=?",
                plan.identity.scope(),
            ).fetchone()[0]
            expected = 1 if previous is None else int(previous) + 1
            if plan.version != expected:
                raise ContractViolation("DAG plan version is not monotonic")
            self._connection.execute(
                "INSERT INTO dag_plans VALUES(?,?,?,?,?,?,?,?,?,?)",
                (*plan.identity.scope(), plan.version, plan.digest, encoded, actor, plan.reason),
            )
            for node in plan.nodes:
                self._connection.execute(
                    "INSERT INTO dag_budget(tenant_id,project_id,task_id,run_id,scope_node_id,node_id,reserved_micros) VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id,run_id,scope_node_id,node_id) DO UPDATE SET reserved_micros=excluded.reserved_micros",
                    (*plan.identity.scope(), node.node_id, node.budget_micros),
                )

    def consume_budget(
        self,
        identity: Identity,
        node_id: str,
        cost_micros: int,
        *,
        global_limit_micros: int,
        idempotency_key: str,
    ) -> None:
        if (
            cost_micros < 0
            or global_limit_micros < 0
            or not idempotency_key
            or len(idempotency_key.encode("utf-8")) > 256
        ):
            raise ContractViolation("DAG budget values or idempotency key are invalid")
        with self._transaction():
            self._assert_run_scope(identity)
            prior = self._connection.execute(
                "SELECT node_id,cost_micros,global_limit_micros FROM dag_budget_mutations WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND idempotency_key=?",
                (*identity.scope(), idempotency_key),
            ).fetchone()
            if prior is not None:
                if (prior["node_id"], int(prior["cost_micros"]), int(prior["global_limit_micros"])) != (
                    node_id,
                    cost_micros,
                    global_limit_micros,
                ):
                    raise ContractViolation("DAG budget idempotency key was reused with different content")
                return
            row = self._connection.execute(
                "SELECT reserved_micros,used_micros FROM dag_budget WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?",
                (*identity.scope(), node_id),
            ).fetchone()
            total = int(
                self._connection.execute(
                    "SELECT COALESCE(SUM(used_micros),0) FROM dag_budget WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=?",
                    identity.scope(),
                ).fetchone()[0]
            )
            if (
                row is None
                or int(row["used_micros"]) + cost_micros > int(row["reserved_micros"])
                or total + cost_micros > global_limit_micros
            ):
                raise BudgetExceeded("DAG node or global budget exceeded")
            self._connection.execute(
                "UPDATE dag_budget SET used_micros=used_micros+? WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?",
                (cost_micros, *identity.scope(), node_id),
            )
            self._connection.execute(
                "INSERT INTO dag_budget_mutations VALUES(?,?,?,?,?,?,?,?,?)",
                (*identity.scope(), idempotency_key, node_id, cost_micros, global_limit_micros),
            )

    def lock_resource(self, identity: Identity, resource: str, owner_node: str) -> None:
        if not resource or not owner_node:
            raise ContractViolation("workspace lock requires resource and owner")
        with self._lock:
            self._assert_run_scope(identity)
            row = self._connection.execute(
                "SELECT owner_node FROM workspace_locks WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND resource=?",
                (*identity.scope(), resource),
            ).fetchone()
            if row is not None and row["owner_node"] != owner_node:
                raise ContractViolation("workspace resource is locked by another node")
            if row is not None:
                return
            self._connection.execute(
                "INSERT INTO workspace_locks(tenant_id,project_id,task_id,run_id,scope_node_id,resource,owner_node) VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id,run_id,scope_node_id,resource) DO UPDATE SET version=version+1",
                (*identity.scope(), resource, owner_node),
            )

    def unlock_resource(self, identity: Identity, resource: str, owner_node: str) -> None:
        with self._lock:
            self._assert_run_scope(identity)
            self._connection.execute(
                "DELETE FROM workspace_locks WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND resource=? AND owner_node=?",
                (*identity.scope(), resource, owner_node),
            )

    def register_compensation(
        self, identity: Identity, node_id: str, operation: str, *, idempotency_key: str
    ) -> int:
        if not operation or not idempotency_key or len(idempotency_key.encode("utf-8")) > 256:
            raise ContractViolation("compensation operation and idempotency key are required")
        with self._transaction():
            self._assert_run_scope(identity)
            prior = self._connection.execute(
                "SELECT node_id,sequence,operation FROM dag_compensations WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND idempotency_key=?",
                (*identity.scope(), idempotency_key),
            ).fetchone()
            if prior is not None:
                if (prior["node_id"], prior["operation"]) != (node_id, operation):
                    raise ContractViolation("compensation idempotency key was reused with different content")
                return int(prior["sequence"])
            sequence = int(
                self._connection.execute(
                    "SELECT COALESCE(MAX(sequence),-1)+1 FROM dag_compensations WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=?",
                    (*identity.scope(), node_id),
                ).fetchone()[0]
            )
            self._connection.execute(
                "INSERT INTO dag_compensations(tenant_id,project_id,task_id,run_id,scope_node_id,node_id,sequence,operation,idempotency_key,state,receipt) VALUES(?,?,?,?,?,?,?,?,?,'pending',NULL)",
                (*identity.scope(), node_id, sequence, operation, idempotency_key),
            )
            return sequence

    def compensate(
        self, identity: Identity, callbacks: Mapping[str, Callable[[str, str], str]]
    ) -> tuple[str, ...]:
        self._assert_run_scope(identity)
        rows = self._connection.execute(
            "SELECT * FROM dag_compensations WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND state IN ('pending','executing','unknown') ORDER BY sequence DESC,node_id DESC",
            identity.scope(),
        ).fetchall()
        receipts: list[str] = []
        for row in rows:
            callback = callbacks.get(row["operation"])
            if callback is None:
                raise NotConfigured("compensation callback is not registered: " + row["operation"])
            self._connection.execute(
                "UPDATE dag_compensations SET state='executing' WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND sequence=? AND state IN ('pending','executing','unknown')",
                (*identity.scope(), row["node_id"], row["sequence"]),
            )
            try:
                receipt = callback(row["node_id"], row["idempotency_key"])
            except Exception:
                self._connection.execute(
                    "UPDATE dag_compensations SET state='unknown' WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND sequence=? AND state='executing'",
                    (*identity.scope(), row["node_id"], row["sequence"]),
                )
                raise
            if not receipt:
                self._connection.execute(
                    "UPDATE dag_compensations SET state='unknown' WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND sequence=? AND state='executing'",
                    (*identity.scope(), row["node_id"], row["sequence"]),
                )
                raise ContractViolation("compensation callback returned no receipt")
            self._connection.execute(
                "UPDATE dag_compensations SET state='completed',receipt=? WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND scope_node_id=? AND node_id=? AND sequence=? AND state='executing'",
                (receipt, *identity.scope(), row["node_id"], row["sequence"]),
            )
            receipts.append(receipt)
        return tuple(receipts)

    def _assert_run_scope(self, identity: Identity) -> None:
        row = self._connection.execute(
            "SELECT project_id,task_id FROM dag_plans WHERE tenant_id=? AND run_id=? AND scope_node_id=? LIMIT 1",
            (identity.tenant_id, identity.run_id, identity.node_id),
        ).fetchone()
        if row is not None and (row["project_id"], row["task_id"]) != (identity.project_id, identity.task_id):
            raise TenantIsolationError("DAG control run is bound to another project/task")


class LocalDagExecutor:
    """Bounded executor for local engineering tests; Temporal remains external."""

    def __init__(self, dag: DurableAgentDag, *, max_concurrency: int = 4) -> None:
        if max_concurrency < 1:
            raise ContractViolation("DAG concurrency must be positive")
        self.dag = dag
        self.max_concurrency = max_concurrency

    def materialize(self, plan: DagPlan) -> None:
        for node in plan.nodes:
            self.dag.add(plan.identity, node.node_id, node.dependencies, budget_micros=node.budget_micros)

    def run(
        self, identity: Identity, worker: Callable[[AgentNode], str], *, owner: str = "local-dag"
    ) -> tuple[AgentNode, ...]:
        completed: list[AgentNode] = []
        while True:
            ready = self.dag.ready(identity)
            if not ready:
                break
            batch = ready[: self.max_concurrency]
            for node in batch:
                claimed = self.dag.claim(identity, node.node_id, owner)
                try:
                    result_ref = worker(claimed)
                except Exception:
                    self.dag.fail(identity, node.node_id, owner, claimed.fencing_token or "")
                    raise
                completed.append(
                    self.dag.complete(identity, node.node_id, owner, claimed.fencing_token or "", result_ref)
                )
        return tuple(completed)


class RepositoryIntegrator(Protocol):
    def create_integration_branch(self, run_id: str, base_revision: str) -> str: ...
    def changed_files(self, revision: str) -> tuple[str, ...]: ...
    def changed_symbols(self, revision: str) -> tuple[str, ...]: ...
    def apply_revision(self, integration_branch: str, revision: str) -> Mapping[str, Any]: ...
    def apply_resolution(
        self, integration_branch: str, resolution: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...
    def head(self, integration_branch: str) -> str: ...
    def rollback(self, integration_branch: str, base_revision: str) -> None: ...


@dataclass(frozen=True, slots=True)
class MergeInput:
    node_id: str
    revision: str
    artifact_ref: str


@dataclass(frozen=True, slots=True)
class MergeResult:
    status: str
    integration_branch: str
    revision: str | None
    file_conflicts: tuple[str, ...]
    symbol_conflicts: tuple[str, ...]
    receipts: tuple[Mapping[str, Any], ...]
    digest: str


class SemanticMergeCoordinator:
    """Integrates child revisions with explicit file/symbol conflict oracles."""

    def __init__(self, repository: RepositoryIntegrator) -> None:
        self.repository = repository

    def integrate(
        self,
        identity: Identity,
        *,
        base_revision: str,
        inputs: Iterable[MergeInput],
        resolve: Callable[[tuple[str, ...], tuple[str, ...], tuple[MergeInput, ...]], Mapping[str, Any]]
        | None,
        verify: Callable[[str], bool],
    ) -> MergeResult:
        values = tuple(inputs)
        if not values or len({item.node_id for item in values}) != len(values) or not base_revision:
            raise ContractViolation("semantic merge inputs are invalid")
        files: dict[str, list[str]] = {}
        symbols: dict[str, list[str]] = {}
        for item in values:
            for path in self.repository.changed_files(item.revision):
                files.setdefault(path, []).append(item.node_id)
            for symbol in self.repository.changed_symbols(item.revision):
                symbols.setdefault(symbol, []).append(item.node_id)
        file_conflicts = tuple(sorted(path for path, owners in files.items() if len(set(owners)) > 1))
        symbol_conflicts = tuple(sorted(symbol for symbol, owners in symbols.items() if len(set(owners)) > 1))
        branch = self.repository.create_integration_branch(identity.run_id, base_revision)
        receipts: list[Mapping[str, Any]] = []
        try:
            if (file_conflicts or symbol_conflicts) and resolve is None:
                self.repository.rollback(branch, base_revision)
                return MergeResult(
                    "blocked",
                    branch,
                    None,
                    file_conflicts,
                    symbol_conflicts,
                    (),
                    digest_of(
                        {
                            "branch": branch,
                            "files": file_conflicts,
                            "symbols": symbol_conflicts,
                            "status": "blocked",
                        }
                    ),
                )
            for item in sorted(values, key=lambda value: value.node_id):
                receipt = dict(self.repository.apply_revision(branch, item.revision))
                if receipt.get("status") != "applied":
                    raise ContractViolation("child revision did not apply cleanly")
                receipts.append(receipt)
            if file_conflicts or symbol_conflicts:
                assert resolve is not None
                resolution = dict(resolve(file_conflicts, symbol_conflicts, values))
                if not resolution.get("approved_by") or not resolution.get("changes"):
                    raise ContractViolation("semantic conflict resolution lacks approval or changes")
                receipts.append(dict(self.repository.apply_resolution(branch, resolution)))
            revision = self.repository.head(branch)
            if not verify(revision):
                raise ContractViolation("integrated revision failed verification")
        except Exception:
            self.repository.rollback(branch, base_revision)
            raise
        body = {
            "branch": branch,
            "revision": revision,
            "files": file_conflicts,
            "symbols": symbol_conflicts,
            "receipts": receipts,
            "status": "succeeded",
        }
        return MergeResult(
            "succeeded", branch, revision, file_conflicts, symbol_conflicts, tuple(receipts), digest_of(body)
        )


class ProviderFallbackPolicy:
    def choose(
        self,
        contract: ChildAgentContract,
        *,
        attempted: Iterable[str],
        available: Mapping[str, Mapping[str, Any]],
    ) -> str:
        attempted_set = set(attempted)
        for provider in contract.provider_preferences:
            capabilities = available.get(provider)
            if provider in attempted_set or capabilities is None:
                continue
            if capabilities.get("contract_version") != "1.0" or capabilities.get("state") != "healthy":
                continue
            return provider
        raise NotConfigured("no compatible child-agent provider fallback remains")


def _identity_dict(identity: Identity) -> dict[str, Any]:
    return {
        "tenant_id": identity.tenant_id,
        "project_id": identity.project_id,
        "task_id": identity.task_id,
        "run_id": identity.run_id,
        "node_id": identity.node_id,
        "agent_id": identity.agent_id,
    }


def _contract_dict(node: ChildAgentContract) -> dict[str, Any]:
    return {
        **asdict(node),
        "workspace_strategy": node.workspace_strategy.value,
        "input_refs": list(node.input_refs),
        "dependencies": list(node.dependencies),
        "provider_preferences": list(node.provider_preferences),
        "output_contract": dict(node.output_contract),
    }


def _plan_dict(plan: DagPlan) -> dict[str, Any]:
    return {
        "identity": _identity_dict(plan.identity),
        "version": plan.version,
        "nodes": [_contract_dict(node) for node in plan.nodes],
        "reason": plan.reason,
        "digest": plan.digest,
    }


def _validate_temporal_plan_payload(value: Any) -> dict[str, Any]:
    """Validate the untyped payload before it can alter durable workflow state."""

    if not isinstance(value, Mapping):
        raise ContractViolation("Temporal DAG plan must be an object")
    plan = dict(value)
    identity = plan.get("identity")
    nodes = plan.get("nodes")
    if not isinstance(identity, Mapping) or not isinstance(nodes, (list, tuple)) or not nodes:
        raise ContractViolation("Temporal DAG identity/nodes are invalid")
    identity_fields = {"tenant_id", "project_id", "task_id", "run_id", "node_id", "agent_id"}
    if set(identity) != identity_fields or any(
        not isinstance(identity.get(name), str) or not identity.get(name)
        for name in identity_fields - {"agent_id"}
    ):
        raise ContractViolation("Temporal DAG identity is incomplete")
    if identity.get("agent_id") is not None and not isinstance(identity.get("agent_id"), str):
        raise ContractViolation("Temporal DAG agent identity is invalid")
    try:
        version = int(plan["version"])
    except (KeyError, TypeError, ValueError) as error:
        raise ContractViolation("Temporal DAG version is invalid") from error
    reason, declared_digest = plan.get("reason"), plan.get("digest")
    if (
        version < 1
        or not isinstance(reason, str)
        or not reason.strip()
        or not isinstance(declared_digest, str)
    ):
        raise ContractViolation("Temporal DAG metadata is invalid")
    node_fields = {
        "node_id",
        "task",
        "input_refs",
        "output_contract",
        "dependencies",
        "workspace_strategy",
        "provider_preferences",
        "budget_micros",
        "max_attempts",
        "compensation",
    }
    normalized_nodes: list[dict[str, Any]] = []
    graph: dict[str, tuple[str, ...]] = {}
    for raw_node in nodes:
        if not isinstance(raw_node, Mapping) or set(raw_node) != node_fields:
            raise ContractViolation("Temporal child-agent contract fields are invalid")
        node = dict(raw_node)
        node_id, task = node.get("node_id"), node.get("task")
        dependencies, inputs, preferences = (
            node.get("dependencies"),
            node.get("input_refs"),
            node.get("provider_preferences"),
        )
        if not isinstance(node_id, str) or not node_id or not isinstance(task, str) or not task.strip():
            raise ContractViolation("Temporal child-agent identity/task is invalid")
        if not isinstance(dependencies, (list, tuple)) or not all(
            isinstance(item, str) for item in dependencies
        ):
            raise ContractViolation("Temporal child-agent dependencies are invalid")
        if not isinstance(inputs, (list, tuple)) or not all(
            isinstance(item, str) and item.startswith(("sha256:", "git:", "artifact:")) for item in inputs
        ):
            raise ContractViolation("Temporal child-agent input references are invalid")
        if not isinstance(preferences, (list, tuple)) or not all(
            isinstance(item, str) and item for item in preferences
        ):
            raise ContractViolation("Temporal child-agent provider preferences are invalid")
        if not isinstance(node.get("output_contract"), Mapping) or not node["output_contract"]:
            raise ContractViolation("Temporal child-agent output contract is invalid")
        if node.get("workspace_strategy") not in {item.value for item in WorkspaceStrategy}:
            raise ContractViolation("Temporal child-agent workspace strategy is invalid")
        if (
            not isinstance(node.get("budget_micros"), int)
            or int(node["budget_micros"]) < 0
            or not isinstance(node.get("max_attempts"), int)
            or int(node["max_attempts"]) < 1
        ):
            raise ContractViolation("Temporal child-agent budget/attempts are invalid")
        if node.get("compensation") is not None and not isinstance(node.get("compensation"), str):
            raise ContractViolation("Temporal child-agent compensation is invalid")
        normalized = {
            **node,
            "input_refs": list(inputs),
            "output_contract": dict(node["output_contract"]),
            "dependencies": list(dependencies),
            "provider_preferences": list(preferences),
        }
        normalized_nodes.append(normalized)
        graph[node_id] = tuple(dependencies)
    if (
        len(graph) != len(normalized_nodes)
        or any(dependency not in graph for dependencies in graph.values() for dependency in dependencies)
        or _cycle(graph)
    ):
        raise ContractViolation("Temporal DAG has duplicate, absent or cyclic dependencies")
    normalized_identity = {
        name: identity.get(name)
        for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id", "agent_id")
    }
    digest_body = {
        "identity": tuple(
            normalized_identity[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id")
        ),
        "version": version,
        "nodes": normalized_nodes,
        "reason": reason,
    }
    if digest_of(digest_body) != declared_digest:
        raise ContractViolation("Temporal DAG digest is invalid")
    return {
        "identity": normalized_identity,
        "version": version,
        "nodes": normalized_nodes,
        "reason": reason,
        "digest": declared_digest,
    }


def _cycle(graph: Mapping[str, tuple[str, ...]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(dependency) for dependency in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
