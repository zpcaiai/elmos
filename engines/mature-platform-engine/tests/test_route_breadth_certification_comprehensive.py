import unittest
from elmos_mature_platform.types import (
    RouteCertificationStatus,
    MigrationRouteCell
)
from elmos_mature_platform.route_breadth_certification_engine import RouteBreadthCertificationEngine

class TestRouteBreadthCertificationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = RouteBreadthCertificationEngine()

    def _create_cell(self, route_id="r-1", src_lang="Java", tgt_lang="CSharp", src_fw="Spring", tgt_fw="AspNetCore", cov=80.0, syn=85.0, sem=85.0):
        return MigrationRouteCell(
            route_id=route_id,
            source_language=src_lang,
            target_language=tgt_lang,
            source_framework=src_fw,
            target_framework=tgt_fw,
            status=RouteCertificationStatus.NOT_EVALUATED,
            test_coverage_pct=cov,
            syntax_fidelity_score=syn,
            semantic_equivalence_score=sem
        )

    def test_register_and_get_route(self):
        cell = self._create_cell()
        self.engine.register_route(cell)
        retrieved = self.engine.get_route("r-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.source_language, "Java")
        self.assertEqual(retrieved.target_language, "CSharp")

    def test_register_duplicate_id_raises(self):
        cell = self._create_cell()
        self.engine.register_route(cell)
        with self.assertRaises(ValueError):
            self.engine.register_route(cell)

    def test_register_duplicate_pair_raises(self):
        cell1 = self._create_cell("r-1")
        cell2 = self._create_cell("r-2")
        self.engine.register_route(cell1)
        with self.assertRaises(ValueError):
            self.engine.register_route(cell2)

    def test_find_route_by_pair(self):
        cell = self._create_cell()
        self.engine.register_route(cell)
        found = self.engine.find_route_by_pair("java", "csharp", "spring", "aspnetcore")
        self.assertIsNotNone(found)
        self.assertEqual(found.route_id, "r-1")

    def test_list_routes_filters(self):
        self.engine.register_route(self._create_cell("r-1", src_lang="Java", tgt_lang="CSharp"))
        self.engine.register_route(self._create_cell("r-2", src_lang="Python", tgt_lang="Go"))
        self.engine.register_route(self._create_cell("r-3", src_lang="Java", tgt_lang="TypeScript"))

        java_routes = self.engine.list_routes(source_language="Java")
        self.assertEqual(len(java_routes), 2)

        go_routes = self.engine.list_routes(target_language="Go")
        self.assertEqual(len(go_routes), 1)

    def test_evaluate_certification_full_pass(self):
        cell = self._create_cell(cov=90.0, syn=95.0, sem=95.0)
        self.engine.register_route(cell)
        certified = self.engine.evaluate_certification("r-1", certifier="e5-gate")
        self.assertEqual(certified.status, RouteCertificationStatus.CERTIFIED)
        self.assertEqual(certified.certifier, "e5-gate")
        self.assertTrue(certified.certified_at)

    def test_evaluate_certification_provisional(self):
        cell = self._create_cell(cov=75.0, syn=80.0, sem=70.0)
        self.engine.register_route(cell)
        certified = self.engine.evaluate_certification("r-1")
        self.assertEqual(certified.status, RouteCertificationStatus.PROVISIONAL)

    def test_evaluate_certification_candidate(self):
        cell = self._create_cell(cov=40.0, syn=50.0, sem=40.0)
        self.engine.register_route(cell)
        certified = self.engine.evaluate_certification("r-1")
        self.assertEqual(certified.status, RouteCertificationStatus.CANDIDATE)

    def test_deprecate_route(self):
        cell = self._create_cell()
        self.engine.register_route(cell)
        dep = self.engine.deprecate_route("r-1", reason="Replaced by unified polyglot route")
        self.assertEqual(dep.status, RouteCertificationStatus.DEPRECATED)
        self.assertTrue(any("DEPRECATED" in lim for lim in dep.known_limitations))

    def test_generate_matrix_report(self):
        c1 = self._create_cell("r-1", src_lang="Java", tgt_lang="CSharp", cov=95.0, syn=95.0, sem=95.0)
        c2 = self._create_cell("r-2", src_lang="Python", tgt_lang="Rust", cov=70.0, syn=75.0, sem=70.0)
        c3 = self._create_cell("r-3", src_lang="C", tgt_lang="Rust", cov=30.0, syn=40.0, sem=30.0)

        self.engine.register_route(c1)
        self.engine.register_route(c2)
        self.engine.register_route(c3)

        self.engine.evaluate_certification("r-1")
        self.engine.evaluate_certification("r-2")
        self.engine.evaluate_certification("r-3")

        report = self.engine.generate_matrix_report()
        self.assertEqual(report.total_routes, 3)
        self.assertEqual(report.certified_routes_count, 1)
        self.assertEqual(report.provisional_routes_count, 1)
        self.assertEqual(report.candidate_routes_count, 1)
        self.assertAlmostEqual(report.coverage_breadth_pct, 33.33, places=1)
        self.assertEqual(len(report.language_pairs_supported), 3)

    def test_find_migration_path_direct_and_multihop(self):
        # Setup routes: Java -> Go (certified), Go -> Rust (certified)
        c1 = self._create_cell("r-1", src_lang="Java", tgt_lang="Go", cov=95.0, syn=95.0, sem=95.0)
        c2 = self._create_cell("r-2", src_lang="Go", tgt_lang="Rust", cov=95.0, syn=95.0, sem=95.0)
        self.engine.register_route(c1)
        self.engine.register_route(c2)
        self.engine.evaluate_certification("r-1")
        self.engine.evaluate_certification("r-2")

        # Direct search: Java -> Go
        direct = self.engine.find_migration_path("Java", "Go")
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct[0].route_id, "r-1")

        # Multi-hop search: Java -> Rust (via Go)
        multihop = self.engine.find_migration_path("Java", "Rust")
        self.assertEqual(len(multihop), 2)
        self.assertEqual(multihop[0].route_id, "r-1")
        self.assertEqual(multihop[1].route_id, "r-2")

        # Unconnected: Java -> Swift
        none = self.engine.find_migration_path("Java", "Swift")
        self.assertEqual(len(none), 0)

if __name__ == "__main__":
    unittest.main()
