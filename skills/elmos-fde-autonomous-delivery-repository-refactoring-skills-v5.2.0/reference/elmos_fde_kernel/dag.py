from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

class CycleError(ValueError):
    pass

@dataclass(frozen=True)
class Step:
    step_id: str
    depends_on: tuple[str, ...] = ()
    machine_seconds: float = 0.0

class TransformationDAG:
    def __init__(self, steps: Iterable[Step | dict]) -> None:
        cooked = []
        for item in steps:
            cooked.append(item if isinstance(item, Step) else Step(str(item["step_id"]), tuple(item.get("depends_on", ())), float(item.get("machine_seconds", 0))))
        self.steps = {s.step_id: s for s in cooked}
        if len(self.steps) != len(cooked):
            raise ValueError("duplicate step_id")
        missing = sorted({d for s in cooked for d in s.depends_on if d not in self.steps})
        if missing:
            raise ValueError(f"missing dependencies: {missing}")
        self.topological_order()

    def topological_order(self) -> list[str]:
        indegree = {k: 0 for k in self.steps}
        children: dict[str, list[str]] = defaultdict(list)
        for step in self.steps.values():
            for dep in step.depends_on:
                indegree[step.step_id] += 1
                children[dep].append(step.step_id)
        queue = deque(sorted(k for k, v in indegree.items() if v == 0))
        order = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for child in sorted(children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(order) != len(self.steps):
            raise CycleError("transformation DAG contains a cycle")
        return order

    def critical_path_seconds(self) -> float:
        longest: dict[str, float] = {}
        for step_id in self.topological_order():
            step = self.steps[step_id]
            longest[step_id] = step.machine_seconds + max((longest[d] for d in step.depends_on), default=0.0)
        return max(longest.values(), default=0.0)
