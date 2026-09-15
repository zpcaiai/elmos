"""System landscape topology and dependency graph analyzer."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from .models import DependencyEdge, SystemNode


class DependencyGraphAnalyzer:
    """Analyzes system-level call graphs, database coupling, and cycles."""

    def __init__(self, nodes: List[SystemNode], edges: List[DependencyEdge]):
        self.nodes = {n.nodeId: n for n in nodes}
        self.edges = edges
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
        self.reverse_adj: Dict[str, Set[str]] = defaultdict(set)

        for edge in edges:
            if edge.validity == "ACTIVE":
                self.adjacency[edge.sourceNodeId].add(edge.targetNodeId)
                self.reverse_adj[edge.targetNodeId].add(edge.sourceNodeId)

    def find_strongly_connected_components(self) -> List[List[str]]:
        """Tarjan's algorithm for detecting cyclic dependencies (Composite Migration Units)."""
        index = 0
        indices: Dict[str, int] = {}
        lowlink: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        def strongconnect(v: str):
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in self.adjacency.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])

            if lowlink[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(sorted(scc))

        for node_id in self.nodes:
            if node_id not in indices:
                strongconnect(node_id)

        return sccs

    def detect_shared_database_couplings(self) -> Dict[str, List[str]]:
        """Identifies database nodes with multiple active writing services."""
        db_writers: Dict[str, List[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.validity == "ACTIVE" and edge.edgeType == "WRITES_DB":
                target_node = self.nodes.get(edge.targetNodeId)
                if target_node and target_node.nodeType == "DATABASE":
                    db_writers[edge.targetNodeId].append(edge.sourceNodeId)

        return {db_id: sorted(list(set(writers))) for db_id, writers in db_writers.items() if len(set(writers)) > 1}

    def get_blast_radius(self, node_id: str) -> Set[str]:
        """Calculates all downstream dependents that call into or depend on this node."""
        visited: Set[str] = set()
        queue = deque([node_id])

        while queue:
            curr = queue.popleft()
            for dependent in self.reverse_adj.get(curr, set()):
                if dependent not in visited:
                    visited.add(dependent)
                    queue.append(dependent)

        return visited
