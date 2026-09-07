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


class FanoutCoordinator:
    def __init__(self, *, max_workers: int = 4) -> None:
        if not 1 <= max_workers <= 64:
            raise ValueError("max_workers out of range")
        self.max_workers = max_workers

    @staticmethod
    def validate(assignments: Sequence[AgentAssignment]) -> None:
        workspace_owners: dict[str, str] = {}
        for assignment in assignments:
            previous = workspace_owners.setdefault(assignment.workspace_id, assignment.agent_id)
            if previous != assignment.agent_id:
                raise ValueError("multiple agents cannot share a workspace scope")

    def run(self, assignments: Sequence[AgentAssignment], worker: Callable[[AgentAssignment], T]) -> dict[str, T | Exception]:
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
