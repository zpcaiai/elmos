"""Agent Migration Factory Engine (Batch 42 - Skill 1423).

Coordinates high-throughput multi-agent code migration workflows, wave scheduling,
git worktree allocations, task state machine lifecycles, and rollback checkpoints.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    AgentMigrationTask,
    AgentTaskLifecycle,
    MigrationWavePlan,
)


class AgentMigrationFactoryEngine:
    """Industrial multi-agent code migration factory and task orchestration."""

    def __init__(self) -> None:
        self._waves: Dict[str, MigrationWavePlan] = {}
        self._tasks: Dict[str, AgentMigrationTask] = {}
        self._worktrees: Dict[str, str] = {}

    def create_wave_plan(self, wave: MigrationWavePlan) -> str:
        """Create a scheduled migration wave for grouping related transformation tasks."""
        if wave.wave_number < 0:
            raise ValueError("wave_number must be non-negative")

        if not wave.wave_id:
            wave.wave_id = f"wave-{uuid.uuid4().hex[:8]}"

        wave.status = "pending"
        self._waves[wave.wave_id] = wave
        return wave.wave_id

    def dispatch_task(self, task: AgentMigrationTask) -> str:
        """Dispatch a single transformation task to an allocated agent and worktree."""
        if not task.project_id or not task.wave_id or not task.agent_id:
            raise ValueError("project_id, wave_id, and agent_id are required")
        if not task.source_language or not task.target_language:
            raise ValueError("source_language and target_language are required")

        wave = self._waves.get(task.wave_id)
        if not wave:
            raise ValueError(f"Migration wave not found: {task.wave_id}")

        if not task.task_id:
            task.task_id = f"mtask-{uuid.uuid4().hex[:8]}"

        if not task.assigned_worktree:
            task.assigned_worktree = f"/tmp/elmos_worktrees/{task.task_id}"

        task.status = AgentTaskLifecycle.DISPATCHED
        task.started_at = datetime.now(timezone.utc).isoformat()

        self._tasks[task.task_id] = task
        self._worktrees[task.task_id] = task.assigned_worktree

        if task.task_id not in wave.tasks:
            wave.tasks.append(task.task_id)

        if wave.status == "pending":
            wave.status = "in_progress"
            wave.started_at = task.started_at

        return task.task_id

    def update_task_status(
        self, task_id: str, new_status: AgentTaskLifecycle, error_message: str = ""
    ) -> AgentMigrationTask:
        """Transition task through its execution lifecycle (ANALYZING, TRANSFORMING, etc.)."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Migration task not found: {task_id}")

        task.status = new_status
        task.error_message = error_message

        if new_status in (
            AgentTaskLifecycle.COMPLETED,
            AgentTaskLifecycle.FAILED,
            AgentTaskLifecycle.CANCELLED,
        ):
            task.completed_at = datetime.now(timezone.utc).isoformat()

        return task

    def attach_checkpoint(self, task_id: str, checkpoint_id: str) -> AgentMigrationTask:
        """Bind an intermediate recoverable checkpoint to a running migration task."""
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Migration task not found: {task_id}")
        if not checkpoint_id:
            raise ValueError("checkpoint_id cannot be empty")

        task.checkpoint_id = checkpoint_id
        return task

    def get_wave_progress(self, wave_id: str) -> Dict[str, Any]:
        """Calculate progress and task distribution for a specific wave."""
        wave = self._waves.get(wave_id)
        if not wave:
            raise ValueError(f"Migration wave not found: {wave_id}")

        tasks = [self._tasks[tid] for tid in wave.tasks if tid in self._tasks]
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == AgentTaskLifecycle.COMPLETED)
        failed = sum(1 for t in tasks if t.status == AgentTaskLifecycle.FAILED)
        in_progress = sum(
            1 for t in tasks
            if t.status in (AgentTaskLifecycle.DISPATCHED, AgentTaskLifecycle.ANALYZING,
                           AgentTaskLifecycle.TRANSFORMING, AgentTaskLifecycle.VERIFYING)
        )

        pct = (completed / total * 100.0) if total > 0 else 0.0

        if total > 0 and (completed + failed) == total:
            wave.status = "completed"
            wave.completed_at = datetime.now(timezone.utc).isoformat()

        return {
            "wave_id": wave_id,
            "wave_number": wave.wave_number,
            "status": wave.status,
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "completion_pct": pct,
        }

    def get_task(self, task_id: str) -> Optional[AgentMigrationTask]:
        """Retrieve task details."""
        return self._tasks.get(task_id)

    def get_factory_throughput_report(self) -> Dict[str, Any]:
        """Generate platform migration factory overall throughput and metrics."""
        total_tasks = len(self._tasks)
        completed_tasks = sum(1 for t in self._tasks.values() if t.status == AgentTaskLifecycle.COMPLETED)
        failed_tasks = sum(1 for t in self._tasks.values() if t.status == AgentTaskLifecycle.FAILED)

        lang_pairs: Dict[str, int] = {}
        for t in self._tasks.values():
            pair = f"{t.source_language}->{t.target_language}"
            lang_pairs[pair] = lang_pairs.get(pair, 0) + 1

        return {
            "total_waves": len(self._waves),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_rate_pct": (completed_tasks / (completed_tasks + failed_tasks) * 100.0) if (completed_tasks + failed_tasks) > 0 else 0.0,
            "language_pairs": lang_pairs,
        }
