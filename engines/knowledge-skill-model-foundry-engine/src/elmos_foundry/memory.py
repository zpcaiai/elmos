"""Experience episode memory, trajectory sanitization, and replay store for Elmos Foundry.

Captures agent run trajectories with privacy-preserving redaction and credit assignment.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Mapping, Sequence

from .domain import (
    ConsentStatus,
    ContentDigest,
    ExperienceEpisode,
    RightsClass,
    TenantScope,
)
from .kernel import ExecutionKernel


class ExperienceMemoryStore:
    """Enterprise experience capture and replay memory store."""

    def __init__(self, kernel: ExecutionKernel | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._episodes: dict[str, ExperienceEpisode] = {}

    def capture_episode(
        self,
        task_type: str,
        task_goal: str,
        trajectory: Sequence[Mapping[str, Any]],
        outcome: Mapping[str, Any],
        reward_score: float,
        verifier_evidence: Mapping[str, Any] | None = None,
        release_id: str = "rel-v2.0.0",
        tenant_scope: TenantScope | None = None,
    ) -> ExperienceEpisode:
        scope = tenant_scope or self.kernel.current_tenant
        
        # Privacy-preserving redaction on trajectory
        sanitized_trajectory = [self._sanitize_step(step) for step in trajectory]
        
        ep_id = str(uuid.uuid4())
        episode = ExperienceEpisode(
            episode_id=ep_id,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            release_id=release_id,
            task_type=task_type,
            task_goal=task_goal,
            trajectory=sanitized_trajectory,
            outcome=outcome,
            reward_score=max(0.0, min(1.0, reward_score)),
            verifier_evidence=verifier_evidence or {"verifier": "deterministic", "status": "VERIFIED"},
        )
        self._episodes[ep_id] = episode
        return episode

    def _sanitize_step(self, step: Mapping[str, Any]) -> Mapping[str, Any]:
        """Redact secrets and sensitive tokens from trajectory steps."""
        sanitized = dict(step)
        for key in ["prompt", "input", "output", "code"]:
            if key in sanitized and isinstance(sanitized[key], str):
                # Redact JWT tokens, passwords, bearer tokens, API keys
                text = sanitized[key]
                text = re.sub(r"(Bearer\s+)[A-Za-z0-9\-\._~+/]+=*", r"\1[REDACTED]", text, flags=re.IGNORECASE)
                text = re.sub(r"(password['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED]\2", text, flags=re.IGNORECASE)
                text = re.sub(r"(api[-_]?key['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", r"\1[REDACTED]\2", text, flags=re.IGNORECASE)
                sanitized[key] = text
        return sanitized

    def get_episode(self, episode_id: str, tenant_scope: TenantScope | None = None) -> ExperienceEpisode | None:
        scope = tenant_scope or self.kernel.current_tenant
        ep = self._episodes.get(episode_id)
        if ep is not None and ep.tenant_id == scope.tenant_id:
            return ep
        return None

    def query_high_reward_episodes(
        self,
        min_reward: float = 0.8,
        task_type: str | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> Sequence[ExperienceEpisode]:
        scope = tenant_scope or self.kernel.current_tenant
        results = []
        for ep in self._episodes.values():
            if ep.tenant_id != scope.tenant_id:
                continue
            if ep.reward_score < min_reward:
                continue
            if task_type and ep.task_type != task_type:
                continue
            results.append(ep)
        return results
