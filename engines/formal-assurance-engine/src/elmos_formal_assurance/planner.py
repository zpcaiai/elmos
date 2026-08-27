from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable

from .canonical import digest_value
from .contracts import ProofObligation


class PlanError(ValueError):
    pass


def topological_order(obligations: Iterable[ProofObligation]) -> list[str]:
    items = {item.id: item for item in obligations}
    if len(items) == 0:
        return []
    indegree = {identifier: 0 for identifier in items}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for identifier, obligation in items.items():
        for dependency in obligation.dependencies:
            if dependency == identifier:
                raise PlanError(f"{identifier}: self dependency is forbidden")
            if dependency not in items:
                raise PlanError(f"{identifier}: unknown dependency {dependency}")
            indegree[identifier] += 1
            outgoing[dependency].append(identifier)
    ready = deque(
        sorted(identifier for identifier, count in indegree.items() if count == 0)
    )
    order: list[str] = []
    while ready:
        current = ready.popleft()
        order.append(current)
        for successor in sorted(outgoing[current]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    if len(order) != len(items):
        cycle = sorted(
            identifier for identifier, count in indegree.items() if count > 0
        )
        raise PlanError(f"proof obligation DAG contains a cycle: {cycle}")
    return order


def estimate_wall_clock_seconds(
    obligations: Iterable[ProofObligation],
    historical_seconds: dict[str, int] | None = None,
    max_parallel: int = 1,
) -> int:
    if max_parallel < 1:
        raise PlanError("max_parallel must be positive")
    historical_seconds = historical_seconds or {}
    items = list(obligations)
    durations = [
        max(
            1,
            int(
                historical_seconds.get(
                    item.property_kind, 180 if item.criticality.value == "P0" else 60
                )
            ),
        )
        for item in items
    ]
    if not durations:
        return 0
    return max(max(durations), (sum(durations) + max_parallel - 1) // max_parallel)


def serialize_plan(
    obligations: Iterable[ProofObligation], max_parallel: int = 1
) -> dict:
    items = list(obligations)
    return {
        "order": topological_order(items),
        "obligationIds": [item.id for item in items],
        "estimatedWallClockSeconds": estimate_wall_clock_seconds(
            items, max_parallel=max_parallel
        ),
        "obligationDigest": digest_value([item.id for item in items]),
    }
