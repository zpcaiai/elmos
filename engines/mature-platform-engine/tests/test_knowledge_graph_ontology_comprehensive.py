import unittest
from elmos_mature_platform.knowledge_graph_ontology_engine import KnowledgeGraphOntologyEngine
from elmos_mature_platform.types import (
    OntologyNode, OntologyNodeType, OntologyEdge, OntologyEdgeType
)

class TestKnowledgeGraphOntologyEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeGraphOntologyEngine()

    def test_add_node(self):
        node = OntologyNode(node_id="n1", node_type=OntologyNodeType.FRAMEWORK, name="React")
        res = self.engine.add_node(node)
        self.assertEqual(res, "n1")
        self.assertEqual(self.engine.get_node("n1"), node)

    def test_add_edge_success(self):
        n1 = OntologyNode(node_id="n1", node_type=OntologyNodeType.FRAMEWORK, name="React")
        n2 = OntologyNode(node_id="n2", node_type=OntologyNodeType.LANGUAGE, name="JS")
        self.engine.add_node(n1)
        self.engine.add_node(n2)
        edge = OntologyEdge(edge_id="e1", source_id="n1", target_id="n2", edge_type=OntologyEdgeType.DEPENDS_ON)
        res = self.engine.add_edge(edge)
        self.assertEqual(res, "e1")

    def test_add_edge_missing_source(self):
        n2 = OntologyNode(node_id="n2", node_type=OntologyNodeType.LANGUAGE, name="JS")
        self.engine.add_node(n2)
        edge = OntologyEdge(edge_id="e1", source_id="n1", target_id="n2", edge_type=OntologyEdgeType.DEPENDS_ON)
        with self.assertRaisesRegex(ValueError, "Source node n1 does not exist."):
            self.engine.add_edge(edge)

    def test_add_edge_missing_target(self):
        n1 = OntologyNode(node_id="n1", node_type=OntologyNodeType.FRAMEWORK, name="React")
        self.engine.add_node(n1)
        edge = OntologyEdge(edge_id="e1", source_id="n1", target_id="n2", edge_type=OntologyEdgeType.DEPENDS_ON)
        with self.assertRaisesRegex(ValueError, "Target node n2 does not exist."):
            self.engine.add_edge(edge)

    def test_get_node_missing(self):
        self.assertIsNone(self.engine.get_node("missing"))

    def test_get_neighbors_no_filter(self):
        self._setup_simple_graph()
        neighbors = self.engine.get_neighbors("n1")
        self.assertEqual(len(neighbors), 2)
        node_ids = {n.node_id for n in neighbors}
        self.assertEqual(node_ids, {"n2", "n3"})

    def test_get_neighbors_with_filter(self):
        self._setup_simple_graph()
        neighbors = self.engine.get_neighbors("n1", OntologyEdgeType.DEPENDS_ON)
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].node_id, "n2")

    def test_get_neighbors_missing_node(self):
        self.assertEqual(self.engine.get_neighbors("missing"), [])

    def test_get_neighbors_no_edges(self):
        n = OntologyNode(node_id="n_alone", node_type=OntologyNodeType.LIBRARY, name="Lone")
        self.engine.add_node(n)
        self.assertEqual(self.engine.get_neighbors("n_alone"), [])

    def test_find_migration_path_simple(self):
        self._setup_migration_graph()
        path = self.engine.find_migration_path("n1", "n4")
        self.assertEqual(len(path), 2)
        self.assertEqual(path[0].source_id, "n1")
        self.assertEqual(path[0].target_id, "n2")
        self.assertEqual(path[1].source_id, "n2")
        self.assertEqual(path[1].target_id, "n4")

    def test_find_migration_path_no_path(self):
        self._setup_migration_graph()
        path = self.engine.find_migration_path("n1", "n_disconnected")
        self.assertEqual(path, [])

    def test_find_migration_path_missing_nodes(self):
        self.assertEqual(self.engine.find_migration_path("missing1", "missing2"), [])
        self._setup_migration_graph()
        self.assertEqual(self.engine.find_migration_path("n1", "missing2"), [])

    def test_find_migration_path_cycle(self):
        self._setup_migration_graph()
        # Add a cycle n2 -> n1
        self.engine.add_edge(OntologyEdge("e_cycle", "n2", "n1", OntologyEdgeType.DEPENDS_ON))
        path = self.engine.find_migration_path("n1", "n4")
        # Cycle shouldn't prevent finding path
        self.assertEqual(len(path), 2)

    def test_find_migration_path_same_node(self):
        self._setup_migration_graph()
        path = self.engine.find_migration_path("n1", "n1")
        # Should be empty path to self? Or just empty list. Our logic handles it by returning [] if no valid edge path.
        self.assertEqual(path, [])

    def test_find_migration_path_longer_path(self):
        self._setup_migration_graph()
        path = self.engine.find_migration_path("n1", "n5")
        self.assertEqual(len(path), 2)

    def test_query_by_pattern_any(self):
        self._setup_tags_graph()
        res = self.engine.query_by_pattern(["tag1", "tag3"])
        self.assertEqual(len(res), 3) # n1, n2, n3
        
    def test_query_by_pattern_all(self):
        self._setup_tags_graph()
        res = self.engine.query_by_pattern(["tag1", "tag2"], match_all=True)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].node_id, "n1")

    def test_query_by_pattern_none_found(self):
        self._setup_tags_graph()
        res = self.engine.query_by_pattern(["tag99"])
        self.assertEqual(len(res), 0)

    def test_query_by_pattern_empty_query(self):
        self._setup_tags_graph()
        res = self.engine.query_by_pattern([])
        self.assertEqual(len(res), 0)

    def test_query_by_pattern_match_all_missing(self):
        self._setup_tags_graph()
        res = self.engine.query_by_pattern(["tag1", "tag99"], match_all=True)
        self.assertEqual(len(res), 0)

    def test_find_similar_projects_exact_match(self):
        self._setup_projects_graph()
        props = {"k1": "v1", "k2": "v2", "k3": "v3"}
        res = self.engine.find_similar_projects(props)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0]["node"].node_id, "p1")
        self.assertEqual(res[0]["score"], 1.0)

    def test_find_similar_projects_partial_match(self):
        self._setup_projects_graph()
        props = {"k1": "v1", "k9": "v9"}
        res = self.engine.find_similar_projects(props)
        self.assertEqual(res[0]["node"].node_id, "p1")
        self.assertEqual(res[0]["score"], 1/4) # intersection=1 (k1), union=4 (k1, k9, k2, k3)

    def test_find_similar_projects_no_overlap(self):
        self._setup_projects_graph()
        props = {"kx": "vx"}
        res = self.engine.find_similar_projects(props)
        self.assertEqual(res[0]["score"], 0.0)

    def test_find_similar_projects_empty_query(self):
        self._setup_projects_graph()
        res = self.engine.find_similar_projects({})
        self.assertEqual(res[0]["score"], 0.0)

    def test_get_transitive_dependencies(self):
        self._setup_dependencies_graph()
        deps = self.engine.get_transitive_dependencies("root")
        self.assertEqual(set(deps), {"d1", "d2", "d3", "d4"})

    def test_get_transitive_dependencies_cycle(self):
        self._setup_dependencies_graph()
        self.engine.add_edge(OntologyEdge("e_cyc", "d4", "d1", OntologyEdgeType.DEPENDS_ON))
        deps = self.engine.get_transitive_dependencies("root")
        self.assertEqual(set(deps), {"d1", "d2", "d3", "d4"})

    def test_get_transitive_dependencies_filtered(self):
        self._setup_dependencies_graph()
        # Add non depends_on edge
        self.engine.add_node(OntologyNode("d5", OntologyNodeType.LIBRARY, "d5"))
        self.engine.add_edge(OntologyEdge("e_other", "d1", "d5", OntologyEdgeType.MIGRATES_TO))
        deps = self.engine.get_transitive_dependencies("root")
        self.assertNotIn("d5", deps)

    def test_detect_migration_conflicts_outgoing(self):
        self._setup_conflicts_graph()
        conflicts = self.engine.detect_migration_conflicts("n1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["direction"], "outgoing")
        self.assertEqual(conflicts[0]["conflict_node_id"], "c1")

    def test_detect_migration_conflicts_incoming(self):
        self._setup_conflicts_graph()
        conflicts = self.engine.detect_migration_conflicts("c1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["direction"], "incoming")
        self.assertEqual(conflicts[0]["conflict_node_id"], "n1")

    def test_detect_migration_conflicts_none(self):
        self._setup_conflicts_graph()
        conflicts = self.engine.detect_migration_conflicts("n_safe")
        self.assertEqual(len(conflicts), 0)

    def test_get_ontology_stats(self):
        self._setup_simple_graph()
        stats = self.engine.get_ontology_stats()
        self.assertEqual(stats["total_nodes"], 3)
        self.assertEqual(stats["total_edges"], 2)
        self.assertEqual(stats["nodes_by_type"]["language"], 3)
        self.assertEqual(stats["edges_by_type"]["depends_on"], 1)
        self.assertEqual(stats["edges_by_type"]["migrates_to"], 1)

    def test_add_edge_preserves_order(self):
        self.engine.add_node(OntologyNode("n1", OntologyNodeType.LANGUAGE, "n1"))
        self.engine.add_node(OntologyNode("n2", OntologyNodeType.LANGUAGE, "n2"))
        self.engine.add_edge(OntologyEdge("e1", "n1", "n2", OntologyEdgeType.DEPENDS_ON))
        self.engine.add_edge(OntologyEdge("e2", "n1", "n2", OntologyEdgeType.MIGRATES_TO))
        edges = self.engine._edges["n1"]
        self.assertEqual(edges[0].edge_id, "e1")
        self.assertEqual(edges[1].edge_id, "e2")

    def test_node_type_filtering_on_similar_projects(self):
        self._setup_projects_graph()
        self.engine.add_node(OntologyNode("non_project", OntologyNodeType.LANGUAGE, "x", properties={"k1":"v1"}))
        res = self.engine.find_similar_projects({"k1":"v1"})
        for item in res:
            self.assertEqual(item["node"].node_type, OntologyNodeType.PROJECT)

    def test_find_migration_path_multiple_targets(self):
        self._setup_migration_graph()
        self.engine.add_edge(OntologyEdge("e_direct", "n1", "n4", OntologyEdgeType.MIGRATES_TO))
        path = self.engine.find_migration_path("n1", "n4")
        self.assertEqual(len(path), 1)
        self.assertEqual(path[0].edge_id, "e_direct")

    def test_detect_migration_conflicts_multiple(self):
        self._setup_conflicts_graph()
        self.engine.add_node(OntologyNode("c2", OntologyNodeType.FRAMEWORK, "c2"))
        self.engine.add_edge(OntologyEdge("e_err", "c2", "n1", OntologyEdgeType.CAUSES_ERROR))
        conflicts = self.engine.detect_migration_conflicts("n1")
        self.assertEqual(len(conflicts), 2)
        dirs = {c["direction"] for c in conflicts}
        self.assertEqual(dirs, {"incoming", "outgoing"})

    def _setup_simple_graph(self):
        for i in range(1, 4):
            self.engine.add_node(OntologyNode(f"n{i}", OntologyNodeType.LANGUAGE, f"N{i}"))
        self.engine.add_edge(OntologyEdge("e1", "n1", "n2", OntologyEdgeType.DEPENDS_ON))
        self.engine.add_edge(OntologyEdge("e2", "n1", "n3", OntologyEdgeType.MIGRATES_TO))

    def _setup_migration_graph(self):
        for i in range(1, 6):
            self.engine.add_node(OntologyNode(f"n{i}", OntologyNodeType.FRAMEWORK, f"N{i}"))
        self.engine.add_node(OntologyNode("n_disconnected", OntologyNodeType.FRAMEWORK, "D"))
        
        self.engine.add_edge(OntologyEdge("e1", "n1", "n2", OntologyEdgeType.MIGRATES_TO))
        self.engine.add_edge(OntologyEdge("e2", "n1", "n3", OntologyEdgeType.MIGRATES_TO))
        self.engine.add_edge(OntologyEdge("e3", "n2", "n4", OntologyEdgeType.MIGRATES_TO))
        self.engine.add_edge(OntologyEdge("e4", "n4", "n5", OntologyEdgeType.MIGRATES_TO))
        self.engine.add_edge(OntologyEdge("e5", "n3", "n5", OntologyEdgeType.MIGRATES_TO))

    def _setup_tags_graph(self):
        self.engine.add_node(OntologyNode("n1", OntologyNodeType.LIBRARY, "N1", tags=["tag1", "tag2"]))
        self.engine.add_node(OntologyNode("n2", OntologyNodeType.LIBRARY, "N2", tags=["tag2", "tag3"]))
        self.engine.add_node(OntologyNode("n3", OntologyNodeType.LIBRARY, "N3", tags=["tag1"]))
        self.engine.add_node(OntologyNode("n4", OntologyNodeType.LIBRARY, "N4", tags=["tag4"]))

    def _setup_projects_graph(self):
        self.engine.add_node(OntologyNode("p1", OntologyNodeType.PROJECT, "P1", properties={"k1": "v1", "k2": "v2", "k3": "v3"}))
        self.engine.add_node(OntologyNode("p2", OntologyNodeType.PROJECT, "P2", properties={"k2": "v2", "k4": "v4"}))
        self.engine.add_node(OntologyNode("p3", OntologyNodeType.PROJECT, "P3", properties={"k5": "v5"}))

    def _setup_dependencies_graph(self):
        self.engine.add_node(OntologyNode("root", OntologyNodeType.PROJECT, "Root"))
        self.engine.add_node(OntologyNode("d1", OntologyNodeType.LIBRARY, "D1"))
        self.engine.add_node(OntologyNode("d2", OntologyNodeType.LIBRARY, "D2"))
        self.engine.add_node(OntologyNode("d3", OntologyNodeType.LIBRARY, "D3"))
        self.engine.add_node(OntologyNode("d4", OntologyNodeType.LIBRARY, "D4"))
        
        self.engine.add_edge(OntologyEdge("e1", "root", "d1", OntologyEdgeType.DEPENDS_ON))
        self.engine.add_edge(OntologyEdge("e2", "d1", "d2", OntologyEdgeType.DEPENDS_ON))
        self.engine.add_edge(OntologyEdge("e3", "d1", "d3", OntologyEdgeType.DEPENDS_ON))
        self.engine.add_edge(OntologyEdge("e4", "d2", "d4", OntologyEdgeType.DEPENDS_ON))

    def _setup_conflicts_graph(self):
        self.engine.add_node(OntologyNode("n1", OntologyNodeType.LIBRARY, "N1"))
        self.engine.add_node(OntologyNode("c1", OntologyNodeType.LIBRARY, "C1"))
        self.engine.add_node(OntologyNode("n_safe", OntologyNodeType.LIBRARY, "Safe"))
        self.engine.add_edge(OntologyEdge("e1", "n1", "c1", OntologyEdgeType.MUTUALLY_EXCLUSIVE))
        self.engine.add_edge(OntologyEdge("e2", "n1", "n_safe", OntologyEdgeType.DEPENDS_ON))

if __name__ == "__main__":
    unittest.main()
