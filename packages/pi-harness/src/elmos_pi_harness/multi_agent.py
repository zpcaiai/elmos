"""Bounded fan-out/fan-in planning for independent workspace scopes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class AgentAssignment:
    agent_id: str
    workspace_id: str
    task_id: str

    def __post_init__(self) -> None:
        for value in (self.agent_id, self.workspace_id, self.task_id):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("assignment identities must be non-empty strings")


class FanoutCoordinator:
    def __init__(self, *, max_workers: int = 4) -> None:
        if type(max_workers) is not int or not 1 <= max_workers <= 64:
            raise ValueError("max_workers out of range")
        self.max_workers = max_workers

    @staticmethod
    def validate(assignments: Sequence[AgentAssignment]) -> None:
        agents: set[str] = set()
        workspaces: set[str] = set()
        tasks: set[str] = set()
        for assignment in assignments:
            if assignment.agent_id in agents:
                raise ValueError("agent assignments must be unique")
            if assignment.workspace_id in workspaces:
                raise ValueError("multiple agents cannot share a workspace scope")
            if assignment.task_id in tasks:
                raise ValueError("task assignments must be unique")
            agents.add(assignment.agent_id)
            workspaces.add(assignment.workspace_id)
            tasks.add(assignment.task_id)

    def run(self, assignments: Sequence[AgentAssignment], worker: Callable[[AgentAssignment], T]) -> dict[str, T | Exception]:
        assignments = tuple(assignments)
        self.validate(assignments)
        results: dict[str, T | Exception] = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(assignments))), thread_name_prefix="pi-agent") as pool:
            pending = {pool.submit(worker, assignment): assignment for assignment in assignments}
            for future in as_completed(pending):
                assignment = pending[future]
                try:
                    results[assignment.agent_id] = future.result()
                except Exception as exc:  # noqa: BLE001 - branch failures are returned for supervisor classification
                    results[assignment.agent_id] = exc
        return results
