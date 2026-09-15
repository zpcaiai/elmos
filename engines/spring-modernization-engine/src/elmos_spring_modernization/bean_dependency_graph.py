from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, List, Tuple

MAX_BEANS = 1000

class DependencyType(Enum):
    CONSTRUCTOR = auto()
    FIELD = auto()
    SETTER = auto()
    FACTORY = auto()

@dataclass(frozen=True)
class BeanNode:
    name: str
    type_name: str
    scope: str

@dataclass(frozen=True)
class BeanEdge:
    source: str
    target: str
    dependency_type: DependencyType

@dataclass(frozen=True)
class BeanGraph:
    nodes: list[BeanNode]
    edges: list[BeanEdge]
    cycles: list[list[str]]
    mermaid_diagram: str

class BeanDependencyGraphExtractor:
    """
    Industrial-grade extractor for Spring Bean dependency graphs.
    Computes accurate typed dependencies, detects circular references,
    and generates topological ordering and Mermaid visualizations.
    """

    def extract(self, definitions: list[dict[str, Any]]) -> BeanGraph:
        if len(definitions) > MAX_BEANS:
            raise ValueError(f"Too many beans. Max allowed is {MAX_BEANS}")

        nodes: list[BeanNode] = []
        edges: list[BeanEdge] = []
        node_names: set[str] = set()

        for idx, d in enumerate(definitions):
            name = d.get("name", f"bean_{idx}")
            node_names.add(name)
            nodes.append(BeanNode(
                name=name,
                type_name=d.get("type", "java.lang.Object"),
                scope=d.get("scope", "singleton")
            ))

            for dep in d.get("dependencies", []):
                target = dep.get("target")
                if not target:
                    continue
                dep_type_raw = dep.get("type")
                dep_type = self._parse_dependency_type(dep_type_raw)
                edges.append(BeanEdge(
                    source=name,
                    target=target,
                    dependency_type=dep_type
                ))

        # Real cycle detection
        all_names = [n.name for n in nodes]
        for e in edges:
            if e.target not in node_names:
                all_names.append(e.target)
                node_names.add(e.target)

        cycles = self._detect_cycles(all_names, edges)
        mermaid = self._generate_mermaid(nodes, edges, cycles)

        return BeanGraph(nodes=nodes, edges=edges, cycles=cycles, mermaid_diagram=mermaid)

    def _parse_dependency_type(self, raw: Any) -> DependencyType:
        if isinstance(raw, DependencyType):
            return raw
        if isinstance(raw, str):
            raw_lower = raw.strip().lower()
            if raw_lower in ("constructor", "ctor"):
                return DependencyType.CONSTRUCTOR
            elif raw_lower in ("setter", "method"):
                return DependencyType.SETTER
            elif raw_lower in ("factory", "factory_method", "factorybean"):
                return DependencyType.FACTORY
            elif raw_lower in ("field", "autowired"):
                return DependencyType.FIELD
        return DependencyType.FIELD

    def _detect_cycles(self, node_names: list[str], edges: list[BeanEdge]) -> list[list[str]]:
        adj: dict[str, list[str]] = {n: [] for n in node_names}
        for edge in edges:
            if edge.source in adj:
                adj[edge.source].append(edge.target)

        visited: set[str] = set()
        cycles: list[list[str]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def dfs(current: str, path: list[str], path_set: set[str]) -> None:
            path.append(current)
            path_set.add(current)

            for neighbor in adj.get(current, []):
                if neighbor in path_set:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    # Canonicalize representation for deduplication
                    elements = cycle[:-1]
                    if elements:
                        min_elem = min(elements)
                        min_idx = elements.index(min_elem)
                        canonical = tuple(elements[min_idx:] + elements[:min_idx])
                        if canonical not in seen_signatures:
                            seen_signatures.add(canonical)
                            cycles.append(cycle)
                elif neighbor not in visited:
                    dfs(neighbor, path, path_set)

            path.pop()
            path_set.remove(current)

        for name in node_names:
            if name not in visited:
                dfs(name, [], set())
                visited.add(name)

        return cycles

    def _generate_mermaid(self, nodes: list[BeanNode], edges: list[BeanEdge], cycles: list[list[str]]) -> str:
        lines: list[str] = ["graph TD;"]
        cycle_participants: set[str] = {node for cycle in cycles for node in cycle}

        for node in nodes:
            label = f"{node.name}"
            if node.type_name and node.type_name != "java.lang.Object":
                short_type = node.type_name.split(".")[-1]
                label = f"{node.name}\\n({short_type})"
            lines.append(f"  {node.name}[\"{label}\"];")

        for edge in edges:
            type_label = edge.dependency_type.name
            lines.append(f"  {edge.source} -->|{type_label}| {edge.target};")

        if cycle_participants:
            lines.append("  classDef cycleStyle fill:#ffebee,stroke:#c62828,stroke-width:2px;")
            for participant in sorted(cycle_participants):
                lines.append(f"  class {participant} cycleStyle;")

        return "\n".join(lines) + "\n"

    def topological_order(self, graph: BeanGraph) -> Tuple[List[str], bool]:
        """
        Calculates topological initialization order for beans.
        Returns (ordered_names, is_acyclic).
        If acyclic is False, beans involved in cycles are returned after resolved nodes.
        """
        in_degree: dict[str, int] = {n.name: 0 for n in graph.nodes}
        adj: dict[str, list[str]] = {n.name: [] for n in graph.nodes}

        for edge in graph.edges:
            if edge.target in in_degree:
                in_degree[edge.source] = in_degree.get(edge.source, 0) + 1
            if edge.target in adj:
                adj[edge.target].append(edge.source)

        queue = [name for name, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for dependent in adj.get(curr, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        is_acyclic = len(order) == len(graph.nodes)
        if not is_acyclic:
            remaining = [n.name for n in graph.nodes if n.name not in order]
            order.extend(remaining)

        return order, is_acyclic
