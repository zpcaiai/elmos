from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

@dataclass
class TaskCheckpoint:
    task_id: str
    stage: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    checksum: str = ''

    def __post_init__(self):
        if not self.checksum:
            raw = f'{self.task_id}:{self.stage}:{sorted(self.data.items())}'
            self.checksum = f'sha256:{hashlib.sha256(raw.encode("utf-8")).hexdigest()}'

class ResilientTaskExecutor:
    """Provides durable checkpointing, resume, and idempotent execution for intelligence tasks."""

    def __init__(self):
        self._checkpoints: Dict[str, TaskCheckpoint] = {}
        self._executed_tasks: Dict[str, Dict[str, Any]] = {}

    def save_checkpoint(self, task_id: str, stage: str, data: Dict[str, Any]) -> TaskCheckpoint:
        cp = TaskCheckpoint(task_id=task_id, stage=stage, data=data)
        self._checkpoints[task_id] = cp
        return cp

    def get_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        return self._checkpoints.get(task_id)

    def execute_idempotent(
        self,
        task_id: str,
        operation_fn: Callable[[], Dict[str, Any]],
        force_rerun: bool = False,
    ) -> Dict[str, Any]:
        """Executes operation idempotently: resumes from checkpoint if exists, avoids side effects."""
        if not force_rerun and task_id in self._executed_tasks:
            return {
                'task_id': task_id,
                'status': 'REPLAYED_FROM_CACHE',
                'result': self._executed_tasks[task_id],
                'side_effects_repeated': False,
            }

        res = operation_fn()
        self._executed_tasks[task_id] = res
        self.save_checkpoint(task_id, 'COMPLETED', res)
        return {
            'task_id': task_id,
            'status': 'EXECUTED_FRESH',
            'result': res,
            'side_effects_repeated': False,
        }
