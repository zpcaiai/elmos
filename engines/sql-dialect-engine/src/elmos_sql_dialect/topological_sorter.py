"""Topological dependency sorter for database tables and schema objects.

Ensures that:
1. Tables are created in parent-to-child order (foreign key referenced tables first).
2. Data is loaded in parent-to-child order.
3. Tables are dropped in child-to-parent order (reverse topological order).
4. Circular dependencies are detected and isolated so foreign keys can be deferred.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TableDependencyNode:
    table_name: str
    dependencies: set[str] = field(default_factory=set)  # tables that table_name depends ON (parents)
    dependents: set[str] = field(default_factory=set)    # tables that depend on table_name (children)


@dataclass
class TopologicalPlan:
    ordered_tables: list[str]
    circular_tables: list[str]
    deferred_foreign_keys: list[dict[str, Any]] = field(default_factory=list)


class TableDependencyGraph:
    """Computes execution order for DDL creation, data loading, and teardown."""

    def __init__(self) -> None:
        self.nodes: dict[str, TableDependencyNode] = {}

    @classmethod
    def from_tables(cls, tables: list[Any] | dict[str, Any]) -> TableDependencyGraph:
        """Construct dependency graph directly from inspected TableMeta instances or mapping."""
        graph = cls()
        table_list = list(tables.values()) if isinstance(tables, dict) else list(tables)
        for t in table_list:
            t_name = getattr(t, "name", str(t))
            graph.add_table(t_name)
            fks = getattr(t, "foreign_keys", [])
            for fk in fks:
                parent_name = getattr(fk, "foreign_table", None)
                if parent_name:
                    graph.add_dependency(child_table=t_name, parent_table=parent_name)
        return graph

    def add_table(self, table_name: str) -> None:
        t = table_name.lower()
        if t not in self.nodes:
            self.nodes[t] = TableDependencyNode(table_name=t)

    def add_dependency(self, child_table: str, parent_table: str, fk_info: dict[str, Any] | None = None) -> None:
        """child_table has a foreign key pointing to parent_table."""
        c = child_table.lower()
        p = parent_table.lower()
        self.add_table(c)
        self.add_table(p)
        if c != p:  # Ignore self-references in DAG sort (handled during data load or deferred constraint)
            self.nodes[c].dependencies.add(p)
            self.nodes[p].dependents.add(c)

    def compute_creation_order(self) -> TopologicalPlan:
        """Kahn's algorithm for topological sorting."""
        in_degree: dict[str, int] = {t: len(node.dependencies) for t, node in self.nodes.items()}
        queue: deque[str] = deque([t for t, deg in in_degree.items() if deg == 0])

        ordered: list[str] = []
        while queue:
            current = queue.popleft()
            ordered.append(current)
            for dependent in self.nodes[current].dependents:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        circular = [t for t, deg in in_degree.items() if deg > 0]
        # For remaining circular nodes, add them in arbitrary deterministic order
        for circ in sorted(circular):
            ordered.append(circ)

        return TopologicalPlan(ordered_tables=ordered, circular_tables=circular)

    def compute_drop_order(self) -> list[str]:
        """Reverse topological order for safe table drop without CASCADE."""
        plan = self.compute_creation_order()
        return list(reversed(plan.ordered_tables))
