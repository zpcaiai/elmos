"""Industrial Traceability Matrix and Coverage Gap Analysis Engine.

Provides bidirectional requirement-to-code-to-test dependency graph construction,
transitive closure reachability, untraced requirement detection (gap analysis),
orphan test identification, blast radius impact calculation, and Mermaid export.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class TraceNode:
    """Represents a discrete artifact in the engineering lifecycle."""
    node_id: str
    node_type: str  # 'REQUIREMENT', 'ARCHITECTURE', 'CODE', 'TEST'
    title: str
    attributes: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        payload = f"{self.node_id}:{self.node_type}:{self.title}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TraceEdge:
    """Represents a verified relationship between two engineering artifacts."""
    source_id: str
    target_id: str
    relationship: str  # 'SATISFIES', 'TESTS', 'IMPLEMENTS', 'DEPENDS_ON'


@dataclass
class TraceabilityReport:
    """Summary of requirement-to-test traceability posture."""
    total_requirements: int
    covered_requirements: int
    untraced_requirements: List[str]
    orphan_tests: List[str]
    coverage_ratio: float
    merkle_root: str


class TraceabilityMatrixEngine:
    """Industrial graph engine for bidirectional requirement traceability."""

    def __init__(self) -> None:
        self._nodes: Dict[str, TraceNode] = {}
        self._forward_adj: Dict[str, Set[str]] = defaultdict(set)
        self._backward_adj: Dict[str, Set[str]] = defaultdict(set)
        self._edges: List[TraceEdge] = []

    def add_node(self, node_id: str, node_type: str, title: str, attributes: Optional[Dict[str, Any]] = None) -> TraceNode:
        if not node_id:
            raise ValueError("node_id cannot be empty")
        valid_types = {"REQUIREMENT", "ARCHITECTURE", "CODE", "TEST"}
        if node_type not in valid_types:
            raise ValueError(f"Invalid node_type '{node_type}', must be one of {valid_types}")
        node = TraceNode(
            node_id=node_id,
            node_type=node_type,
            title=title,
            attributes=attributes or {},
        )
        self._nodes[node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, relationship: str) -> TraceEdge:
        if source_id not in self._nodes:
            raise KeyError(f"Source node '{source_id}' does not exist in graph")
        if target_id not in self._nodes:
            raise KeyError(f"Target node '{target_id}' does not exist in graph")
        valid_rel = {"SATISFIES", "TESTS", "IMPLEMENTS", "DEPENDS_ON"}
        if relationship not in valid_rel:
            raise ValueError(f"Invalid relationship '{relationship}', must be one of {valid_rel}")

        edge = TraceEdge(source_id=source_id, target_id=target_id, relationship=relationship)
        self._edges.append(edge)
        self._forward_adj[source_id].add(target_id)
        self._backward_adj[target_id].add(source_id)
        return edge

    def get_forward_reachability(self, start_node_id: str) -> Set[str]:
        """Compute transitive closure of all nodes reachable from start_node_id."""
        if start_node_id not in self._nodes:
            raise KeyError(f"Node '{start_node_id}' does not exist")
        visited: Set[str] = set()
        queue: deque[str] = deque([start_node_id])
        while queue:
            curr = queue.popleft()
            for neighbor in self._forward_adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    def get_backward_reachability(self, start_node_id: str) -> Set[str]:
        """Compute transitive closure of all ancestors reaching start_node_id."""
        if start_node_id not in self._nodes:
            raise KeyError(f"Node '{start_node_id}' does not exist")
        visited: Set[str] = set()
        queue: deque[str] = deque([start_node_id])
        while queue:
            curr = queue.popleft()
            for parent in self._backward_adj[curr]:
                if parent not in visited:
                    visited.add(parent)
                    queue.append(parent)
        return visited

    def find_untraced_requirements(self) -> List[str]:
        """Requirements that do not have any TEST node covering their lifecycle scope."""
        untraced = []
        req_nodes = [n for n in self._nodes.values() if n.node_type == "REQUIREMENT"]
        test_nodes = [n for n in self._nodes.values() if n.node_type == "TEST"]
        for req in req_nodes:
            req_scope = self.get_forward_reachability(req.node_id) | {req.node_id}
            has_test = False
            for test in test_nodes:
                test_targets = self.get_forward_reachability(test.node_id) | self.get_backward_reachability(test.node_id) | {test.node_id}
                if req_scope & test_targets:
                    has_test = True
                    break
            if not has_test:
                untraced.append(req.node_id)
        return sorted(untraced)

    def find_orphan_tests(self) -> List[str]:
        """Tests that do not trace to any REQUIREMENT node."""
        orphans = []
        req_nodes = [n for n in self._nodes.values() if n.node_type == "REQUIREMENT"]
        test_nodes = [n for n in self._nodes.values() if n.node_type == "TEST"]
        for test in test_nodes:
            test_targets = self.get_forward_reachability(test.node_id) | self.get_backward_reachability(test.node_id) | {test.node_id}
            has_req = False
            for req in req_nodes:
                req_scope = self.get_forward_reachability(req.node_id) | {req.node_id}
                if test_targets & req_scope:
                    has_req = True
                    break
            if not has_req:
                orphans.append(test.node_id)
        return sorted(orphans)

    def compute_blast_radius(self, changed_node_id: str) -> Set[str]:
        """Compute all downstream artifacts impacted by a change in changed_node_id."""
        return self.get_forward_reachability(changed_node_id)

    def generate_report(self) -> TraceabilityReport:
        req_ids = [n.node_id for n in self._nodes.values() if n.node_type == "REQUIREMENT"]
        total_reqs = len(req_ids)
        untraced = self.find_untraced_requirements()
        covered = total_reqs - len(untraced)
        ratio = (covered / total_reqs * 100.0) if total_reqs > 0 else 100.0
        orphan_tests = self.find_orphan_tests()

        sorted_nodes = sorted(self._nodes.keys())
        hashes = [self._nodes[k].compute_hash() for k in sorted_nodes]
        combined = ":".join(hashes)
        merkle = hashlib.sha256(combined.encode("utf-8")).hexdigest()

        return TraceabilityReport(
            total_requirements=total_reqs,
            covered_requirements=covered,
            untraced_requirements=untraced,
            orphan_tests=orphan_tests,
            coverage_ratio=round(ratio, 2),
            merkle_root=merkle,
        )

    def export_mermaid(self) -> str:
        """Export graph to Mermaid flowchart format."""
        lines = ["flowchart TD"]
        for nid, node in sorted(self._nodes.items()):
            label = f'"{nid} [{node.node_type}]: {node.title}"'
            lines.append(f"    {nid}[{label}]")
        for edge in sorted(self._edges, key=lambda e: (e.source_id, e.target_id)):
            lines.append(f"    {edge.source_id} -->|{edge.relationship}| {edge.target_id}")
        return "\n".join(lines)
