from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    key: str
    size_bytes: int
    restore_ms: float
    recompute_ms: float
    validation_level: str = "TEST_VERIFIED"

    @property
    def net_saving_ms(self) -> float:
        return self.recompute_ms - self.restore_ms


@dataclass(frozen=True, slots=True)
class PrefetchDecision:
    key: str
    next_use_step: int
    distance: int
    size_bytes: int
    expected_net_saving_ms: float
    priority: float


class FutureUseIndex:
    """Index exact future consumers from a deterministic ELMOS DAG schedule."""

    def __init__(self, scheduled_requirements: Sequence[Iterable[str]]) -> None:
        positions: dict[str, list[int]] = {}
        for step, keys in enumerate(scheduled_requirements):
            for key in set(keys):
                positions.setdefault(key, []).append(step)
        self._positions = positions
        self._length = len(scheduled_requirements)

    def next_use(self, key: str, after_step: int) -> int | None:
        positions = self._positions.get(key)
        if not positions:
            return None
        index = bisect.bisect_right(positions, after_step)
        return positions[index] if index < len(positions) else None

    def protected_keys(self, current_step: int, horizon_steps: int) -> set[str]:
        if horizon_steps < 0:
            raise ValueError("horizon_steps must be non-negative")
        limit = current_step + horizon_steps
        protected: set[str] = set()
        for key in self._positions:
            next_step = self.next_use(key, current_step)
            if next_step is not None and next_step <= limit:
                protected.add(key)
        return protected

    def prefetch_candidates(
        self,
        current_step: int,
        artifacts: Mapping[str, ArtifactInfo],
        *,
        resident_keys: set[str] | None = None,
        bandwidth_budget_bytes: int,
        max_items: int = 16,
        horizon_steps: int = 20,
        minimum_net_saving_ms: float = 0.0,
    ) -> list[PrefetchDecision]:
        if bandwidth_budget_bytes < 0 or max_items < 0 or horizon_steps < 0:
            raise ValueError("budgets and horizons must be non-negative")
        resident = resident_keys or set()
        candidates: list[PrefetchDecision] = []
        for key, artifact in artifacts.items():
            if key in resident or artifact.size_bytes > bandwidth_budget_bytes:
                continue
            next_step = self.next_use(key, current_step)
            if next_step is None:
                continue
            distance = next_step - current_step
            if distance <= 0 or distance > horizon_steps:
                continue
            saving = artifact.net_saving_ms
            if saving < minimum_net_saving_ms:
                continue
            # Prefer early use, high net saving, and low transfer size.
            priority = saving / max(1, artifact.size_bytes) / distance
            candidates.append(
                PrefetchDecision(
                    key=key,
                    next_use_step=next_step,
                    distance=distance,
                    size_bytes=artifact.size_bytes,
                    expected_net_saving_ms=saving,
                    priority=priority,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item.priority,
                item.next_use_step,
                item.size_bytes,
                item.key,
            )
        )
        selected: list[PrefetchDecision] = []
        used = 0
        for candidate in candidates:
            if len(selected) >= max_items:
                break
            if used + candidate.size_bytes > bandwidth_budget_bytes:
                continue
            selected.append(candidate)
            used += candidate.size_bytes
        return selected

    def eviction_order(
        self,
        current_step: int,
        artifacts: Mapping[str, ArtifactInfo],
        resident_keys: Iterable[str],
        *,
        protected_keys: set[str] | None = None,
    ) -> list[str]:
        protected = protected_keys or set()

        def rank(key: str) -> tuple[int, float, str]:
            artifact = artifacts[key]
            next_step = self.next_use(key, current_step)
            distance = (self._length + 1) if next_step is None else (next_step - current_step)
            value_density = max(artifact.net_saving_ms, 0.0) / max(1, artifact.size_bytes)
            # Higher distance and lower value density should be evicted first.
            return (distance, -value_density, key)

        candidates = [
            key for key in resident_keys if key in artifacts and key not in protected
        ]
        return sorted(candidates, key=rank, reverse=True)
