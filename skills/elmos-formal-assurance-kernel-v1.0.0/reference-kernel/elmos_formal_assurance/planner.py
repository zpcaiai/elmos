from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import asdict
from typing import Iterable
from .models import ProofObligation

class PlanError(ValueError):
    pass

def topological_order(obligations: Iterable[ProofObligation]) -> list[str]:
    items = {o.id: o for o in obligations}
    indegree = {oid: 0 for oid in items}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for oid, obligation in items.items():
        for dep in obligation.dependencies:
            if dep not in items:
                raise PlanError(f"{oid}: unknown dependency {dep}")
            indegree[oid] += 1
            outgoing[dep].append(oid)
    ready = deque(sorted(k for k, v in indegree.items() if v == 0))
    order: list[str] = []
    while ready:
        current = ready.popleft()
        order.append(current)
        for nxt in sorted(outgoing[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(items):
        cycle = sorted(k for k, v in indegree.items() if v > 0)
        raise PlanError(f"proof obligation DAG contains a cycle: {cycle}")
    return order

def estimate_machine_wall_clock_seconds(
    obligations: Iterable[ProofObligation],
    historical_seconds: dict[str, int] | None = None,
    max_parallel: int = 4,
) -> int:
    if max_parallel < 1:
        raise PlanError("max_parallel must be positive")
    historical_seconds = historical_seconds or {}
    durations = []
    for o in obligations:
        default = 180 if o.criticality.value == "P0" else 60
        durations.append(max(1, historical_seconds.get(o.property_kind, default)))
    if not durations:
        return 0
    return max(max(durations), (sum(durations) + max_parallel - 1) // max_parallel)

def serialize_plan(obligations: Iterable[ProofObligation]) -> dict:
    obs = list(obligations)
    return {
        "order": topological_order(obs),
        "obligations": [asdict(o) for o in obs],
        "estimatedWallClockSeconds": estimate_machine_wall_clock_seconds(obs),
    }
