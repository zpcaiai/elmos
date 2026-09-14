"""Pure DAG scheduling logic; durable task state remains in DurableStore."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from typing import Any


def _graph(nodes: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for node in nodes:
        if not isinstance(node, Mapping):
            raise ValueError("DAG nodes must be objects")
        identity = node.get("id")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("DAG node id must be a non-empty string")
        if identity in values:
            raise ValueError("DAG contains a duplicate node: " + identity)
        aliases: list[set[str]] = []
        for key in ("depends_on", "dependencies"):
            if key not in node:
                continue
            dependencies = node[key]
            if not isinstance(dependencies, (list, tuple, set, frozenset)):
                raise ValueError("DAG dependencies must be a collection of node ids")
            if any(not isinstance(dep, str) or not dep.strip() for dep in dependencies):
                raise ValueError("DAG dependency ids must be non-empty strings")
            if len(set(dependencies)) != len(dependencies):
                raise ValueError("DAG contains duplicate dependencies")
            aliases.append(set(dependencies))
        if len(aliases) == 2 and aliases[0] != aliases[1]:
            raise ValueError("DAG dependency aliases disagree")
        values[identity] = aliases[0] if aliases else set()
    return values


def ready_nodes(nodes: Iterable[Mapping[str, Any]], completed: set[str]) -> list[str]:
    values = _graph(nodes)
    _validate_graph(values)
    if not isinstance(completed, (set, frozenset)) or not completed.issubset(values):
        raise ValueError("completed nodes must belong to the DAG")
    if any(not values[node].issubset(completed) for node in completed):
        raise ValueError("completed nodes must include their dependencies")
    return sorted(node for node, deps in values.items() if node not in completed and deps.issubset(completed))


def validate_acyclic(nodes: Iterable[Mapping[str, Any]]) -> None:
    _validate_graph(_graph(nodes))


def _validate_graph(values: Mapping[str, set[str]]) -> None:
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
