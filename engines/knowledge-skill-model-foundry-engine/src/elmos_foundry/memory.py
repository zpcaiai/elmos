"""Bounded trajectory capture with explicit authorization and scoped replay."""

from __future__ import annotations

import re
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence, cast

from .authorizations import AuthorizationVerifier, require_authorization
from .canonical import canonical_digest, canonical_value
from .domain import CertificationStatus, EvidenceState, ExperienceEpisode, TenantScope
from .kernel import ExecutionKernel

_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:password|api[-_]?key|secret|token)\s*[:=]\s*)[^\s,;]+"),
)
_SECRET_KEY = re.compile(
    r"(?i)(?:^|[-_])(authorization|cookie|credential|password|private[-_]?key|secret|token|api[-_]?key)(?:$|[-_])"
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(r"\1[REDACTED]", result)
        return result
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]"
            if isinstance(key, str) and _SECRET_KEY.search(key)
            else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redact(child) for child in value]
    return value


class ExperienceMemoryStore:
    """Local engineering memory; capture never establishes independent evidence."""

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        capture_verifier: AuthorizationVerifier | None = None,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._capture_verifier = capture_verifier
        self._episodes: dict[tuple[str, str, str], ExperienceEpisode] = {}
        self._lock = RLock()

    def capture_episode(
        self,
        task_type: str,
        task_goal: str,
        trajectory: Sequence[Mapping[str, Any]],
        outcome: Mapping[str, Any],
        reward_score: float,
        verifier_evidence: Mapping[str, Any] | None = None,
        release_id: str = "unbound-release",
        tenant_scope: TenantScope | None = None,
        *,
        capture_authorization_digest: str,
    ) -> ExperienceEpisode:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.experience.capture")
        if not isinstance(task_type, str) or not task_type.strip():
            raise ValueError("task_type must be a non-empty string")
        if not isinstance(task_goal, str) or not task_goal.strip():
            raise ValueError("task_goal must be a non-empty string")
        if not isinstance(trajectory, Sequence) or isinstance(trajectory, (str, bytes)):
            raise TypeError("trajectory must be a sequence of objects")
        if not 1 <= len(trajectory) <= 2048 or any(not isinstance(step, Mapping) for step in trajectory):
            raise ValueError("trajectory must contain 1..2048 object steps")
        subject_digest = canonical_digest(
            {
                "task_type": task_type,
                "task_goal": task_goal,
                "trajectory": trajectory,
                "outcome": outcome,
                "reward_score": reward_score,
                "release_id": release_id,
            }
        )
        authorization = require_authorization(
            self._capture_verifier,
            authorization_type="experience-capture",
            receipt_digest=capture_authorization_digest,
            request={"subject_digest": subject_digest, "release_id": release_id},
            scope=scope,
        )
        sanitized_goal = _redact(task_goal)
        sanitized_value = canonical_value([_redact(step) for step in trajectory])
        normalized_outcome_value = canonical_value(_redact(outcome))
        claimed_verifier_value = canonical_value(_redact(verifier_evidence or {}))
        if not isinstance(sanitized_value, list) or any(
            not isinstance(step, dict) for step in sanitized_value
        ):
            raise ValueError("trajectory did not canonicalize to object steps")
        if not isinstance(normalized_outcome_value, dict):
            raise ValueError("outcome did not canonicalize to an object")
        if not isinstance(claimed_verifier_value, dict):
            raise ValueError("verifier evidence did not canonicalize to an object")
        sanitized = cast(list[dict[str, Any]], sanitized_value)
        normalized_outcome = cast(dict[str, Any], normalized_outcome_value)
        claimed_verifier = cast(dict[str, Any], claimed_verifier_value)
        identity = canonical_digest(
            {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "release_id": release_id,
                "task_type": task_type,
                "task_goal": sanitized_goal,
                "trajectory": sanitized,
                "outcome": normalized_outcome,
                "reward_score": reward_score,
                "capture_authorization_digest": capture_authorization_digest,
                "capture_request_digest": authorization.request_digest,
            }
        )
        episode_id = "ep-" + identity.removeprefix("sha256:")[:32]
        episode = ExperienceEpisode(
            episode_id=episode_id,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            release_id=release_id,
            task_type=task_type,
            task_goal=cast(str, sanitized_goal),
            trajectory=tuple(sanitized),
            outcome=MappingProxyType(dict(normalized_outcome)),
            reward_score=reward_score,
            verifier_evidence=MappingProxyType(
                {
                    "claim": claimed_verifier,
                    "independent_verification": "NOT_RUN",
                    "secret_redaction": "LOCAL_HEURISTIC_SELF_ATTESTED",
                    "capture_authorization_digest": capture_authorization_digest,
                    "capture_request_digest": authorization.request_digest,
                }
            ),
            evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
            certification_status=CertificationStatus.NOT_CERTIFIED,
        )
        with self._lock:
            self._episodes[(scope.tenant_id, scope.project_id, episode_id)] = episode
        return episode

    def get_episode(
        self, episode_id: str, tenant_scope: TenantScope | None = None
    ) -> ExperienceEpisode | None:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.experience.read")
        with self._lock:
            return self._episodes.get((scope.tenant_id, scope.project_id, episode_id))

    def query_high_reward_episodes(
        self,
        min_reward: float = 0.8,
        task_type: str | None = None,
        tenant_scope: TenantScope | None = None,
        *,
        limit: int = 100,
    ) -> Sequence[ExperienceEpisode]:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.experience.read")
        if not 0 <= min_reward <= 1 or not 1 <= limit <= 1000:
            raise ValueError("reward and query limit are outside bounds")
        with self._lock:
            matches = sorted(
                (
                    episode
                    for (tenant, project, _), episode in self._episodes.items()
                    if tenant == scope.tenant_id
                    and project == scope.project_id
                    and episode.reward_score >= min_reward
                    and (task_type is None or episode.task_type == task_type)
                ),
                key=lambda item: item.episode_id,
            )
        return tuple(matches[:limit])


__all__ = ["ExperienceMemoryStore"]
