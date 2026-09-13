import collections
from typing import Any, Dict, List, Optional, Set

from elmos_mature_platform.types import (
    OntologyNode,
    OntologyNodeType,
    OntologyEdge,
    OntologyEdgeType,
)


class KnowledgeGraphOntologyEngine:
    """Knowledge graph ontology engine for migration planning and analysis."""

    def __init__(self) -> None:
        """Initialize the engine with empty in-memory structures."""
        self._nodes: Dict[str, OntologyNode] = {}
        # adjacency list: source_id -> list of edges
        self._edges: Dict[str, List[OntologyEdge]] = collections.defaultdict(list)
        # reverse adjacency list to easily find incoming conflicts etc, if needed
        self._incoming_edges: Dict[str, List[OntologyEdge]] = collections.defaultdict(list)

    def add_node(self, node: OntologyNode) -> str:
        """
        Store a node in the graph and return its ID.
        """
        self._nodes[node.node_id] = node
        return node.node_id

    def add_edge(self, edge: OntologyEdge) -> str:
        """
        Store an edge in the graph. Source and target must exist.
        """
        if edge.source_id not in self._nodes:
            raise ValueError(f"Source node {edge.source_id} does not exist.")
        if edge.target_id not in self._nodes:
            raise ValueError(f"Target node {edge.target_id} does not exist.")
        
        self._edges[edge.source_id].append(edge)
        self._incoming_edges[edge.target_id].append(edge)
        return edge.edge_id

    def get_node(self, node_id: str) -> Optional[OntologyNode]:
        """
        Retrieve a node by its ID.
        """
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str, edge_type: Optional[OntologyEdgeType] = None) -> List[OntologyNode]:
        """
        Target nodes connected from node_id (optionally filtered by edge_type).
        """
        if node_id not in self._nodes:
            return []
        
        neighbors = []
        for edge in self._edges[node_id]:
            if edge_type is None or edge.edge_type == edge_type:
                neighbors.append(self._nodes[edge.target_id])
        return neighbors

    def find_migration_path(self, source_node_id: str, target_node_id: str) -> List[OntologyEdge]:
        """
        Breadth-First Search (BFS) for the shortest path of edges from source to target.
        """
        if source_node_id not in self._nodes or target_node_id not in self._nodes:
            return []

        queue = collections.deque([[source_node_id]])
        visited = {source_node_id}
        # map node_id -> incoming edge used to reach it
        parent_edge_map: Dict[str, OntologyEdge] = {}

        found = False
        while queue:
            path = queue.popleft()
            current = path[-1]

            if current == target_node_id:
                found = True
                break

            for edge in self._edges[current]:
                if edge.target_id not in visited:
                    visited.add(edge.target_id)
                    parent_edge_map[edge.target_id] = edge
                    queue.append(path + [edge.target_id])

        if not found:
            return []

        # Reconstruct path
        edge_path = []
        curr = target_node_id
        while curr != source_node_id:
            edge = parent_edge_map[curr]
            edge_path.append(edge)
            curr = edge.source_id
            
        return list(reversed(edge_path))

    def query_by_pattern(self, pattern_tags: List[str], match_all: bool = False) -> List[OntologyNode]:
        """
        Return nodes matching any or all pattern tags.
        """
        if not pattern_tags:
            return []
        
        results = []
        pattern_set = set(pattern_tags)
        
        for node in self._nodes.values():
            node_tags_set = set(node.tags)
            if match_all:
                if pattern_set.issubset(node_tags_set):
                    results.append(node)
            else:
                if not pattern_set.isdisjoint(node_tags_set):
                    results.append(node)
                    
        return results

    def find_similar_projects(self, project_properties: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Compare PROJECT nodes with properties using matching keys overlap ratio.
        """
        project_keys = set(project_properties.keys())
        similarities = []
        
        for node in self._nodes.values():
            if node.node_type == OntologyNodeType.PROJECT:
                node_keys = set(node.properties.keys())
                intersection = len(project_keys.intersection(node_keys))
                union = len(project_keys.union(node_keys))
                score = intersection / union if union > 0 else 0.0
                
                similarities.append({
                    "node": node,
                    "score": score
                })
                
        similarities.sort(key=lambda x: x["score"], reverse=True)
        return similarities[:top_k]

    def get_transitive_dependencies(self, node_id: str) -> List[str]:
        """
        Traverse DEPENDS_ON edges recursively to find all transitive dependencies.
        Returns a list of node IDs.
        """
        dependencies = set()
        visited = set()
        
        def dfs(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            
            for edge in self._edges.get(current_id, []):
                if edge.edge_type == OntologyEdgeType.DEPENDS_ON:
                    if edge.target_id not in dependencies:
                        dependencies.add(edge.target_id)
                        dfs(edge.target_id)
                        
        dfs(node_id)
        return list(dependencies)

    def detect_migration_conflicts(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Find edges of type MUTUALLY_EXCLUSIVE or CAUSES_ERROR connected to node_id.
        Considers both outgoing and incoming edges.
        """
        conflicts = []
        conflict_types = {OntologyEdgeType.MUTUALLY_EXCLUSIVE, OntologyEdgeType.CAUSES_ERROR}
        
        for edge in self._edges.get(node_id, []):
            if edge.edge_type in conflict_types:
                conflicts.append({
                    "edge": edge,
                    "direction": "outgoing",
                    "conflict_node_id": edge.target_id
                })
                
        for edge in self._incoming_edges.get(node_id, []):
            if edge.edge_type in conflict_types:
                conflicts.append({
                    "edge": edge,
                    "direction": "incoming",
                    "conflict_node_id": edge.source_id
                })
                
        return conflicts

    def get_ontology_stats(self) -> Dict[str, Any]:
        """
        Total nodes, total edges, breakdown by node_type, breakdown by edge_type.
        """
        node_type_counts = collections.Counter(node.node_type.value for node in self._nodes.values())
        
        edge_type_counts = collections.Counter()
        total_edges = 0
        for edge_list in self._edges.values():
            for edge in edge_list:
                edge_type_counts[edge.edge_type.value] += 1
                total_edges += 1
                
        return {
            "total_nodes": len(self._nodes),
            "total_edges": total_edges,
            "nodes_by_type": dict(node_type_counts),
            "edges_by_type": dict(edge_type_counts)
        }
