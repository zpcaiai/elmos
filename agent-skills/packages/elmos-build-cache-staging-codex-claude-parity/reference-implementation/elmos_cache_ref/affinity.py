from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class WorkerCandidate:
    target_id: str
    compatible: bool
    healthy: bool
    prompt_value_ms: float = 0.0
    environment_value_ms: float = 0.0
    artifact_value_ms: float = 0.0
    dag_next_use_value_ms: float = 0.0
    queue_penalty_ms: float = 0.0
    transfer_penalty_ms: float = 0.0
    failure_penalty_ms: float = 0.0
    fairness_penalty_ms: float = 0.0

    @property
    def score(self) -> float:
        if not self.compatible or not self.healthy:
            return float("-inf")
        return (
            self.prompt_value_ms
            + self.environment_value_ms
            + self.artifact_value_ms
            + self.dag_next_use_value_ms
            - self.queue_penalty_ms
            - self.transfer_penalty_ms
            - self.failure_penalty_ms
            - self.fairness_penalty_ms
        )


@dataclass(frozen=True)
class AffinityDecision:
    selected_target: str | None
    ranked_targets: tuple[str, ...]
    reason_codes: tuple[str, ...]


def choose_target(candidates: Iterable[WorkerCandidate]) -> AffinityDecision:
    eligible = sorted(
        (candidate for candidate in candidates if candidate.compatible and candidate.healthy),
        key=lambda candidate: (-candidate.score, candidate.target_id),
    )
    if not eligible:
        return AffinityDecision(None, (), ("NO_COMPATIBLE_TARGET",))
    selected = eligible[0]
    reasons: list[str] = []
    if selected.prompt_value_ms > 0:
        reasons.append("PREFIX_LOCAL")
    if selected.environment_value_ms > 0:
        reasons.append("ENV_LOCAL")
    if selected.artifact_value_ms > 0:
        reasons.append("ARTIFACT_LOCAL")
    if selected.dag_next_use_value_ms > 0:
        reasons.append("DAG_NEXT_USE")
    if selected.fairness_penalty_ms > 0:
        reasons.append("FAIRNESS_APPLIED")
    return AffinityDecision(selected.target_id, tuple(item.target_id for item in eligible), tuple(reasons))
