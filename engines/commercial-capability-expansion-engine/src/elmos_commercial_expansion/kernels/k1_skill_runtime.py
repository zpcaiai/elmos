"""K1: Skill Runtime Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from ..models import Checkpoint, KernelType, Priority, SkillDefinition, TaskContext


class SkillRuntimeKernel:
    """Provides universal skill execution, progressive disclosure, checkpointing, and routing."""

    def __init__(self, registry: Optional[List[SkillDefinition]] = None):
        self.registry: Dict[str, SkillDefinition] = {s.id: s for s in (registry or [])}
        self.checkpoints: Dict[str, List[Checkpoint]] = {}
        self.active_runs: Dict[str, Dict[str, Any]] = {}

    def register_skill(self, skill: SkillDefinition) -> None:
        self.registry[skill.id] = skill

    def discover_skills(
        self,
        context: TaskContext,
        max_results: int = 10,
        kernel_filter: Optional[KernelType] = None,
    ) -> List[SkillDefinition]:
        """Progressively discloses skills based on relevance to task context."""
        matches: List[tuple[int, SkillDefinition]] = []
        obj_lower = context.objective.lower()

        for skill in self.registry.values():
            if kernel_filter and skill.kernel != kernel_filter:
                continue
            score = 0
            # P0 priority boost
            if skill.priority == Priority.P0:
                score += 5
            # Keyword matching
            skill_tokens = (skill.name + " " + skill.objective).lower().split()
            for token in set(skill_tokens):
                if len(token) > 3 and token in obj_lower:
                    score += 2
            matches.append((score, skill))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in matches[:max_results]]

    def create_checkpoint(
        self,
        task_id: str,
        step_number: int,
        state_snapshot: Dict[str, Any],
        completed_steps: List[str],
        next_step: str,
    ) -> Checkpoint:
        """Persists deterministic execution checkpoint."""
        cp_id = f"cp-{task_id}-s{step_number}-{int(time.time() * 1000)}"
        cp = Checkpoint(
            checkpoint_id=cp_id,
            task_id=task_id,
            step_number=step_number,
            state_snapshot=state_snapshot,
            completed_steps=completed_steps,
            next_step=next_step,
        )
        if task_id not in self.checkpoints:
            self.checkpoints[task_id] = []
        self.checkpoints[task_id].append(cp)
        return cp

    def restore_checkpoint(self, task_id: str, checkpoint_id: str) -> Optional[Checkpoint]:
        """Supports time-travel replay from an earlier validated checkpoint."""
        cps = self.checkpoints.get(task_id, [])
        for cp in cps:
            if cp.checkpoint_id == checkpoint_id:
                return cp
        return None

    def route_execution(
        self,
        context: TaskContext,
        skill: SkillDefinition,
    ) -> Dict[str, Any]:
        """Routes execution to optimal model and tool profiles based on budget and complexity."""
        model_tier = "standard-reasoning"
        if skill.priority == Priority.P0 and context.budget_usd > 2.0:
            model_tier = "advanced-reasoning"

        sandbox_required = skill.kernel in (
            KernelType.K4_BUILD_EXECUTION,
            KernelType.K5_VERIFICATION,
            KernelType.K7_DATABASE_DATA,
        )

        return {
            "skill_id": skill.id,
            "kernel": skill.kernel.value,
            "routed_model_tier": model_tier,
            "sandbox_required": sandbox_required,
            "budget_tokens_allocated": min(context.budget_tokens, 16_000),
            "timeout_seconds": min(context.timeout_seconds, 120),
            "status": "ROUTED",
        }
