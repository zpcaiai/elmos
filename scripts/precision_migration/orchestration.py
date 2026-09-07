#!/usr/bin/env python3
"""Executable, identity-bound DAG orchestration for all PM B01-B44 Skills."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from scripts.precision_migration.domain import DomainExecutionError, _write
from scripts.precision_migration.runtime import canonical_digest
from scripts.precision_migration.trust import verify_content_reference


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATORS_PATH = (
    ROOT / "docs" / "precision-migration-b01-44" / "orchestrator-implementations.json"
)
EXPECTED_ORCHESTRATORS = 45
MAX_EXECUTION_NODES = 64
ORCHESTRATION_ACTIONS = {"plan", "preflight", "execute"}


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class OrchestratorRegistry:
    def __init__(self, payload: dict[str, Any]) -> None:
        if payload.get("schema_version") != 1 or payload.get("namespace") != "precision-migration-b01-44":
            raise DomainExecutionError("orchestrator registry identity is invalid")
        implementations = payload.get("orchestrators")
        if not isinstance(implementations, list) or len(implementations) != EXPECTED_ORCHESTRATORS:
            raise DomainExecutionError("orchestrator registry must contain exactly 45 implementations")
        self.by_handler: dict[str, dict[str, Any]] = {}
        entrypoints: set[str] = set()
        for implementation in implementations:
            checked = dict(implementation)
            observed = checked.pop("implementation_digest", None)
            if observed != _digest(checked):
                raise DomainExecutionError(f"orchestrator digest mismatch: {implementation.get('skill')}")
            handler_id = implementation.get("handler_id")
            entrypoint = implementation.get("handler_entrypoint")
            if not isinstance(handler_id, str) or not isinstance(entrypoint, str):
                raise DomainExecutionError("orchestrator identity is invalid")
            if handler_id in self.by_handler or entrypoint in entrypoints:
                raise DomainExecutionError("orchestrator identities must be unique")
            nodes = implementation.get("nodes")
            edges = implementation.get("edges")
            if not isinstance(nodes, list) or not nodes or len(nodes) != len(set(nodes)):
                raise DomainExecutionError(f"orchestrator nodes are invalid: {handler_id}")
            if not isinstance(edges, list):
                raise DomainExecutionError(f"orchestrator edges are invalid: {handler_id}")
            node_set = set(nodes)
            if any(
                not isinstance(edge, dict)
                or edge.get("from") not in node_set
                or edge.get("to") not in node_set
                or edge.get("from") == edge.get("to")
                for edge in edges
            ):
                raise DomainExecutionError(f"orchestrator edge escapes its DAG: {handler_id}")
            self.by_handler[handler_id] = implementation
            entrypoints.add(entrypoint)

    @classmethod
    def load(cls, path: Path = ORCHESTRATORS_PATH) -> "OrchestratorRegistry":
        return cls(json.loads(path.read_text(encoding="utf-8")))


_REGISTRY: OrchestratorRegistry | None = None


def registry() -> OrchestratorRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = OrchestratorRegistry.load()
    return _REGISTRY


def _topological(nodes: list[str], edges: list[dict[str, str]]) -> list[str]:
    incoming = {node: 0 for node in nodes}
    outgoing = {node: [] for node in nodes}
    for edge in edges:
        incoming[edge["to"]] += 1
        outgoing[edge["from"]].append(edge["to"])
    ready = sorted(node for node, count in incoming.items() if count == 0)
    ordered: list[str] = []
    while ready:
        node = ready.pop(0)
        ordered.append(node)
        for target in sorted(outgoing[node]):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
        ready.sort()
    if len(ordered) != len(nodes):
        raise DomainExecutionError("orchestrator graph contains a cycle")
    return ordered


def _checkpoint(
    request: dict[str, Any],
    parameters: dict[str, Any],
    profile: dict[str, Any],
    selected_set: set[str],
    evidence_roots: tuple[Path, ...],
) -> tuple[set[str], list[dict[str, Any]]]:
    index = parameters.get("checkpoint_asset_index")
    if index is None:
        return set(), []
    assets = request.get("inputs", {}).get("assets", [])
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(assets):
        raise DomainExecutionError("checkpoint_asset_index is invalid")
    reference = assets[index]
    try:
        verify_content_reference(reference, evidence_roots)
        parsed = urlparse(reference["uri"])
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ValueError("checkpoint must be a local content-addressed file")
        payload = json.loads(Path(unquote(parsed.path)).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise DomainExecutionError(f"orchestrator checkpoint verification failed: {exc}") from exc
    if (
        payload.get("skill") != profile["skill"]
        or payload.get("handler_id") != profile["handler_id"]
        or payload.get("dag_digest") != profile["dag_digest"]
        or payload.get("action") != "execute"
    ):
        raise DomainExecutionError("orchestrator checkpoint identity mismatch")
    successful: set[str] = set()
    receipts: list[dict[str, Any]] = []
    for run in payload.get("node_runs", []):
        if not isinstance(run, dict) or run.get("state") not in {"SUCCEEDED", "REUSED_CHECKPOINT"}:
            continue
        node = run.get("node")
        if node not in selected_set or node in successful:
            raise DomainExecutionError("orchestrator checkpoint node set is invalid")
        if not isinstance(run.get("result_digest"), str) or not run["result_digest"].startswith("sha256:"):
            raise DomainExecutionError("orchestrator checkpoint result digest is invalid")
        artifacts = run.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise DomainExecutionError("orchestrator checkpoint lacks child artifacts")
        try:
            for artifact in artifacts:
                verify_content_reference(artifact, evidence_roots)
        except (OSError, ValueError) as exc:
            raise DomainExecutionError(f"orchestrator checkpoint child artifact failed verification: {exc}") from exc
        successful.add(node)
        receipts.append(
            {
                "node": node,
                "state": "REUSED_CHECKPOINT",
                "handler_id": run.get("handler_id"),
                "result_digest": run["result_digest"],
                "artifacts": artifacts,
                "exit_code": 0,
            }
        )
    return successful, receipts


def execute_orchestrator_dag(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    *,
    expected_skill: str,
    expected_handler_id: str,
    expected_implementation_digest: str,
    skill_registry: Any = None,
    evidence_roots: tuple[Path, ...] = (),
    trust_store: Any = None,
    **_: Any,
) -> dict[str, Any]:
    if entry.get("skill") != expected_skill or entry.get("handler_id") != expected_handler_id:
        raise DomainExecutionError("orchestrator handler identity mismatch")
    profile = registry().by_handler.get(expected_handler_id)
    if profile is None:
        raise DomainExecutionError("orchestrator implementation is not allowlisted")
    if (
        profile.get("skill") != expected_skill
        or profile.get("implementation_digest") != expected_implementation_digest
        or profile.get("handler_entrypoint") != entry.get("handler_entrypoint")
    ):
        raise DomainExecutionError("orchestrator profile binding mismatch")
    inputs = request.get("inputs") if isinstance(request.get("inputs"), dict) else {}
    parameters = inputs.get("parameters") if isinstance(inputs.get("parameters"), dict) else {}
    action = parameters.get("orchestration_action", "plan")
    if action not in ORCHESTRATION_ACTIONS:
        raise DomainExecutionError("orchestration_action must be plan, preflight, or execute")
    nodes = list(profile["nodes"])
    selected = parameters.get("selected_nodes", nodes)
    completed = parameters.get("completed_nodes", [])
    failed = parameters.get("failed_nodes", [])
    if not all(isinstance(value, list) for value in (selected, completed, failed)):
        raise DomainExecutionError("orchestrator node selections must be arrays")
    node_set = set(nodes)
    selected_set = set(selected)
    completed_set = set(completed)
    failed_set = set(failed)
    if (
        len(selected_set) != len(selected)
        or len(completed_set) != len(completed)
        or len(failed_set) != len(failed)
        or not selected_set <= node_set
        or not completed_set <= selected_set
        or not failed_set <= selected_set
        or completed_set & failed_set
    ):
        raise DomainExecutionError("orchestrator node selection is invalid")
    edges = [
        edge for edge in profile["edges"]
        if edge["from"] in selected_set and edge["to"] in selected_set
    ]
    order = _topological([node for node in nodes if node in selected_set], edges)
    prerequisites = {node: set() for node in selected_set}
    for edge in edges:
        prerequisites[edge["to"]].add(edge["from"])
    ready = [
        node for node in order
        if node not in completed_set
        and node not in failed_set
        and prerequisites[node] <= completed_set
        and not (prerequisites[node] & failed_set)
    ]
    blocked = [
        node for node in order
        if node not in completed_set and node not in failed_set and node not in ready
    ]
    state = "BLOCKED" if failed_set else "COMPLETE" if completed_set == selected_set else "RUNNABLE"
    preflight: list[dict[str, Any]] = []
    node_runs: list[dict[str, Any]] = []
    if action in {"preflight", "execute"}:
        if skill_registry is None:
            raise DomainExecutionError("orchestrator preflight requires the installed Skill registry")
        from scripts.precision_migration.adapters import AdapterRegistry, execute, resolve_handler

        adapter_registry = AdapterRegistry.load()
        for node in order:
            child_entry = adapter_registry.resolve(node, skill_registry)
            child_handler = resolve_handler(child_entry)
            if child_handler is None:
                raise DomainExecutionError(f"orchestrator child has no allowlisted handler: {node}")
            preflight.append(
                {
                    "node": node,
                    "handler_id": child_entry["handler_id"],
                    "handler_entrypoint": child_entry["handler_entrypoint"],
                    "supported_modes": child_entry["supported_modes"],
                    "maturity": child_entry["maturity"],
                    "state": "READY",
                }
            )
        if action == "execute":
            if completed or failed:
                raise DomainExecutionError("execute action derives completed and failed nodes from child receipts")
            if len(order) > MAX_EXECUTION_NODES:
                raise DomainExecutionError("orchestrator selection exceeds the execution-node budget")
            successful, checkpoint_runs = _checkpoint(request, parameters, profile, selected_set, evidence_roots)
            node_requests = parameters.get("node_requests")
            pending_set = selected_set - successful
            if not isinstance(node_requests, dict) or set(node_requests) != pending_set:
                raise DomainExecutionError("execute action requires exactly one node_requests entry per pending node")
            checkpoint_by_node = {run["node"]: run for run in checkpoint_runs}
            execution_failed: set[str] = set()
            for index, node in enumerate(order):
                if node in successful:
                    node_runs.append(checkpoint_by_node[node])
                    continue
                if not prerequisites[node] <= successful:
                    node_runs.append({"node": node, "state": "BLOCKED_BY_PREREQUISITE"})
                    continue
                child_request = node_requests[node]
                if not isinstance(child_request, dict) or child_request.get("skill") != node:
                    raise DomainExecutionError(f"orchestrator child request identity mismatch: {node}")
                node_root = output_dir / "nodes" / f"{index:03d}-{node}"
                child_result = execute(
                    child_request,
                    node_root,
                    evidence_roots=evidence_roots,
                    trust_store=trust_store,
                    adapter_registry=adapter_registry,
                    skill_registry=skill_registry,
                )
                succeeded = child_result.get("execution_state") == "LOCAL_EXECUTED" and child_result.get("exit_code") == 0
                if succeeded:
                    successful.add(node)
                else:
                    execution_failed.add(node)
                node_runs.append(
                    {
                        "node": node,
                        "state": "SUCCEEDED" if succeeded else "FAILED",
                        "handler_id": child_result.get("handler_id"),
                        "result_digest": child_result.get("result_digest"),
                        "artifacts": child_result.get("artifacts", []),
                        "exit_code": child_result.get("exit_code"),
                    }
                )
            completed_set = successful
            failed_set = execution_failed
            ready = []
            blocked = [node for node in order if node not in successful and node not in execution_failed]
            state = "BLOCKED" if execution_failed or blocked else "COMPLETE"
    body = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": expected_skill,
        "source_skill": profile["source_skill"],
        "handler_id": expected_handler_id,
        "implementation_digest": expected_implementation_digest,
        "dag_digest": profile["dag_digest"],
        "state": state,
        "topological_order": order,
        "ready_nodes": ready,
        "blocked_nodes": blocked,
        "completed_nodes": [node for node in order if node in completed_set],
        "failed_nodes": [node for node in order if node in failed_set],
        "action": action,
        "preflight": preflight,
        "node_runs": node_runs,
        "edges": edges,
        "execution_scope": "LOCAL_DAG_EXECUTION" if action == "execute" else "LOCAL_DAG_PREFLIGHT" if action == "preflight" else "LOCAL_DAG_STATE_MACHINE",
        "production_execution": "NOT_RUN",
        "external_verification": "NOT_RUN",
    }
    body["result_digest"] = canonical_digest(body)
    failed_execution = action == "execute" and state != "COMPLETE"
    return {
        "execution_state": "FAILED" if failed_execution else "LOCAL_EXECUTED",
        "artifacts": [_write(output_dir / "orchestrator-execution.json", body)],
        "exit_code": 4 if failed_execution else 0,
    }


Handler = Callable[..., dict[str, Any]]
