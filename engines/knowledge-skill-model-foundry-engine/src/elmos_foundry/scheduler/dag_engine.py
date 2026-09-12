from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

class CycleError(Exception):
    """Raised when a cycle is detected in the task dependency graph."""
    pass

@dataclass
class TaskNode:
    task_id: str
    dependencies: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    estimated_duration: float = 1.0
    tags: Set[str] = field(default_factory=set)

@dataclass
class TaskWave:
    wave_index: int
    tasks: List[TaskNode] = field(default_factory=list)

class DAGEngine:
    """Directed Acyclic Graph resolver for distributed execution."""

    def __init__(self) -> None:
        self.nodes: Dict[str, TaskNode] = {}
        self.dependents: Dict[str, Set[str]] = {}

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.task_id] = node
        if node.task_id not in self.dependents:
            self.dependents[node.task_id] = set()
        for dep in node.dependencies:
            if dep not in self.dependents:
                self.dependents[dep] = set()
            self.dependents[dep].add(node.task_id)

    def validate_acyclic(self) -> None:
        visited: Dict[str, int] = {}  # 0: visiting, 1: visited
        path: List[str] = []

        def dfs(curr: str) -> None:
            visited[curr] = 0
            path.append(curr)
            node = self.nodes.get(curr)
            if node:
                for dep in node.dependencies:
                    if dep not in self.nodes:
                        # Missing dependency
                        raise ValueError(f"Task {curr} depends on unknown task {dep}")
                    if visited.get(dep) == 0:
                        cycle = path[path.index(dep):] + [dep]
                        raise CycleError(f"Cycle detected: {' -> '.join(cycle)}")
                    if dep not in visited:
                        dfs(dep)
            path.pop()
            visited[curr] = 1

        for task_id in list(self.nodes.keys()):
            if task_id not in visited:
                dfs(task_id)

    def compute_waves(self) -> List[TaskWave]:
        """Partitions nodes into waves of independent tasks that can run in parallel."""
        self.validate_acyclic()

        # In-degree computation (number of unmet dependencies)
        in_degree: Dict[str, int] = {t: len(node.dependencies) for t, node in self.nodes.items()}
        waves: List[TaskWave] = []
        completed: Set[str] = set()

        wave_idx = 0
        while len(completed) < len(self.nodes):
            current_wave_tasks: List[TaskNode] = []
            for t_id, deg in list(in_degree.items()):
                if deg == 0 and t_id not in completed:
                    current_wave_tasks.append(self.nodes[t_id])

            if not current_wave_tasks:
                raise CycleError("Unresolvable cycle or deadlock encountered during wave computation")

            waves.append(TaskWave(wave_index=wave_idx, tasks=current_wave_tasks))
            for task in current_wave_tasks:
                completed.add(task.task_id)
                for dep_on_me in self.dependents.get(task.task_id, set()):
                    in_degree[dep_on_me] -= 1

            wave_idx += 1

        return waves

    def get_ready_tasks(self, completed_task_ids: Set[str], running_task_ids: Set[str]) -> List[TaskNode]:
        ready: List[TaskNode] = []
        for t_id, node in self.nodes.items():
            if t_id in completed_task_ids or t_id in running_task_ids:
                continue
            # Check if all dependencies are in completed_task_ids
            if all(dep in completed_task_ids for dep in node.dependencies):
                ready.append(node)
        return ready

    def dynamic_replan(self, failed_task_id: str, replacement_nodes: List[TaskNode]) -> None:
        """Replaces or patches nodes dynamically upon failure or compensation."""
        if failed_task_id in self.nodes:
            del self.nodes[failed_task_id]
        for r_node in replacement_nodes:
            self.add_node(r_node)
        self.validate_acyclic()
