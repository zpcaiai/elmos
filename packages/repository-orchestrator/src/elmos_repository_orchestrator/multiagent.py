"""Bounded multi-agent DAG coordination with independent verification."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, MutableSet, Sequence

from .contracts import ContractError, require_mapping, require_string


AgentHandler = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class AgentRole:
    name: str
    identity: str
    allowed_tools: frozenset[str]
    handler: AgentHandler
    max_parallel: int = 1

    def __post_init__(self) -> None:
        require_string(self.name, "role.name")
        require_string(self.identity, "role.identity")
        if not self.allowed_tools:
            raise ContractError("role_tools_empty", "agent role requires an exact tool allowlist")
        if not 1 <= self.max_parallel <= 16:
            raise ContractError("invalid_role_parallelism", "role max_parallel must be between 1 and 16")


@dataclass(frozen=True, slots=True)
class AgentAssignment:
    task_id: str
    role: str
    required_tools: frozenset[str]
    idempotency_key: str
    dependencies: tuple[str, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    requires_human_approval: bool = False

    def __post_init__(self) -> None:
        for field_name in ("task_id", "role", "idempotency_key"):
            require_string(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    task_id: str
    role: str
    status: str
    evidence_digest: str | None
    deduplicated: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MultiAgentReport:
    status: str
    outcomes: tuple[AgentOutcome, ...]
    duplicate_side_effects: int
    waves: tuple[tuple[str, ...], ...]


class GovernedMultiAgentCoordinator:
    def __init__(
        self,
        roles: Sequence[AgentRole],
        *,
        verifier: AgentHandler,
        verifier_identity: str,
        completed_effects: MutableSet[str] | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self.roles = {role.name: role for role in roles}
        if not self.roles or len(self.roles) != len(roles):
            raise ContractError("invalid_agent_roles", "agent roles must be non-empty and unique")
        self.verifier = verifier
        self.verifier_identity = require_string(verifier_identity, "verifier_identity")
        if self.verifier_identity in {role.identity for role in roles}:
            raise ContractError("verifier_not_independent", "multi-agent verifier must be independent from workers")
        if not 1 <= max_concurrency <= 32:
            raise ContractError("invalid_agent_concurrency", "max_concurrency must be between 1 and 32")
        self.max_concurrency = max_concurrency
        self.completed_effects = completed_effects if completed_effects is not None else set()
        self._effect_lock = threading.Lock()
        self._semaphores = {name: threading.BoundedSemaphore(role.max_parallel) for name, role in self.roles.items()}

    def _waves(self, assignments: Sequence[AgentAssignment]) -> tuple[tuple[str, ...], ...]:
        tasks = {assignment.task_id: assignment for assignment in assignments}
        if len(tasks) != len(assignments):
            raise ContractError("duplicate_agent_task", "agent task ids must be unique")
        effect_keys = [assignment.idempotency_key for assignment in assignments]
        if len(set(effect_keys)) != len(effect_keys):
            raise ContractError("duplicate_agent_effect", "agent assignments must use unique idempotency keys")
        for assignment in assignments:
            if assignment.role not in self.roles:
                raise ContractError("unknown_agent_role", f"unknown agent role: {assignment.role}")
            missing = sorted(set(assignment.dependencies) - tasks.keys())
            if missing:
                raise ContractError("unknown_agent_dependency", "unknown task dependencies: " + ", ".join(missing))
            forbidden = sorted(assignment.required_tools - self.roles[assignment.role].allowed_tools)
            if forbidden:
                raise ContractError("agent_tool_forbidden", "role lacks required tools: " + ", ".join(forbidden))
        remaining = set(tasks)
        complete: set[str] = set()
        waves: list[tuple[str, ...]] = []
        while remaining:
            ready = tuple(sorted(task_id for task_id in remaining if set(tasks[task_id].dependencies) <= complete))
            if not ready:
                raise ContractError("agent_dependency_cycle", "agent assignment graph contains a cycle")
            waves.append(ready)
            complete.update(ready)
            remaining.difference_update(ready)
        return tuple(waves)

    def _run_one(
        self,
        assignment: AgentAssignment,
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str,
        human_approved_tasks: frozenset[str],
    ) -> AgentOutcome:
        role = self.roles[assignment.role]
        if assignment.requires_human_approval and assignment.task_id not in human_approved_tasks:
            return AgentOutcome(assignment.task_id, assignment.role, "BLOCKED", None, reasons=("human_approval_required",))
        with self._effect_lock:
            if assignment.idempotency_key in self.completed_effects:
                return AgentOutcome(assignment.task_id, assignment.role, "VERIFIED", None, deduplicated=True)
        trusted = {
            "task_id": assignment.task_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "revision_id": revision_id,
            "required_tools": sorted(assignment.required_tools),
            "idempotency_key": assignment.idempotency_key,
            "payload": dict(assignment.payload),
        }
        with self._semaphores[assignment.role]:
            output = require_mapping(role.handler(trusted), "agent.output")
        if output.get("idempotency_key") != assignment.idempotency_key:
            raise ContractError("idempotency_key_mismatch", "agent changed the assigned idempotency key")
        evidence = require_string(output.get("evidence_digest"), "agent.output.evidence_digest")
        if not evidence.startswith("sha256:") or len(evidence) != 71:
            raise ContractError("invalid_evidence_digest", "agent evidence digest is invalid")
        verification = require_mapping(
            self.verifier({"assignment": trusted, "worker_identity": role.identity, "output": dict(output)}),
            "agent.verification",
        )
        if not isinstance(verification.get("passed"), bool):
            raise ContractError("invalid_agent_verification", "agent verifier must return a boolean passed field")
        if verification["passed"] is not True:
            return AgentOutcome(
                assignment.task_id,
                assignment.role,
                "FAILED",
                evidence,
                reasons=tuple(str(value) for value in verification.get("reasons", ())),
            )
        with self._effect_lock:
            self.completed_effects.add(assignment.idempotency_key)
        return AgentOutcome(assignment.task_id, assignment.role, "VERIFIED", evidence)

    def run(
        self,
        assignments: Sequence[AgentAssignment],
        *,
        tenant_id: str,
        project_id: str,
        revision_id: str,
        human_approved_tasks: frozenset[str] = frozenset(),
    ) -> MultiAgentReport:
        scope = tuple(require_string(value, "agent.scope") for value in (tenant_id, project_id, revision_id))
        waves = self._waves(assignments)
        by_id = {assignment.task_id: assignment for assignment in assignments}
        outcomes: dict[str, AgentOutcome] = {}
        for wave in waves:
            runnable = [
                task_id
                for task_id in wave
                if all(outcomes[dependency].status == "VERIFIED" for dependency in by_id[task_id].dependencies)
            ]
            for task_id in set(wave) - set(runnable):
                assignment = by_id[task_id]
                outcomes[task_id] = AgentOutcome(
                    task_id, assignment.role, "BLOCKED", None, reasons=("dependency_not_verified",)
                )
            with ThreadPoolExecutor(max_workers=min(self.max_concurrency, max(1, len(runnable)))) as pool:
                future_map = {
                    task_id: pool.submit(
                        self._run_one,
                        by_id[task_id],
                        tenant_id=scope[0],
                        project_id=scope[1],
                        revision_id=scope[2],
                        human_approved_tasks=human_approved_tasks,
                    )
                    for task_id in runnable
                }
                for task_id in sorted(future_map):
                    outcomes[task_id] = future_map[task_id].result()
        ordered = tuple(outcomes[assignment.task_id] for assignment in assignments)
        status = "VERIFIED" if all(outcome.status == "VERIFIED" for outcome in ordered) else "BLOCKED"
        return MultiAgentReport(
            status=status,
            outcomes=ordered,
            duplicate_side_effects=0,
            waves=waves,
        )
