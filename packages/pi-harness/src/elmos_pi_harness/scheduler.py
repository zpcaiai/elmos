"""Pure DAG scheduling logic; durable task state remains in DurableStore."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from typing import Any


def ready_nodes(nodes: Iterable[Mapping[str, Any]], completed: set[str]) -> list[str]:
    values = {str(node["id"]): set(node.get("depends_on", node.get("dependencies", []))) for node in nodes}
    unknown = sorted(dep for deps in values.values() for dep in deps if dep not in values)
    if unknown:
        raise ValueError("DAG references unknown nodes: " + ",".join(sorted(set(unknown))))
    indegree = {node: len(deps - completed) for node, deps in values.items() if node not in completed}
    if any(node in completed for node in values):
        indegree.update({node: 0 for node in completed})
    return sorted(node for node, count in indegree.items() if node not in completed and count == 0)


def validate_acyclic(nodes: Iterable[Mapping[str, Any]]) -> None:
    values = {str(node["id"]): set(node.get("depends_on", node.get("dependencies", []))) for node in nodes}
    indegree = {key: len(value) for key, value in values.items()}
    children: dict[str, list[str]] = defaultdict(list)
    for child, parents in values.items():
        for parent in parents:
            if parent not in values:
                raise ValueError("DAG references unknown node: " + parent)
            children[parent].append(child)
    queue = deque(node for node, count in indegree.items() if count == 0)
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if seen != len(values):
        raise ValueError("DAG contains a cycle")
