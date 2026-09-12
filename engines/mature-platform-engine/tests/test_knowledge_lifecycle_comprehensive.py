"""Tests for Knowledge Flywheel and Product Lifecycle Engines."""

import unittest

from elmos_mature_platform.types import (
    KnowledgeConfidence,
    KnowledgeEntry,
    MigrationPattern,
    PredictionResult,
    ApiChangeType,
    ReleaseChannel,
    SupportStatus,
    ApiCompatibilityCheck,
    DeprecationRecord,
    ReleaseCandidate,
    SupportPolicy,
)
from elmos_mature_platform.knowledge_flywheel_engine import KnowledgeFlywheelEngine
from elmos_mature_platform.product_lifecycle_engine import ProductLifecycleEngine


class TestKnowledgeFlywheelEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeFlywheelEngine()

    def test_ingest_and_query_knowledge_entry(self):
        entry = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry)
        results = self.engine.query_knowledge("java", "go")
        self.assertEqual(len(results), 1)

    def test_query_with_technology_filter(self):
        entry = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry)
        results = self.engine.query_knowledge("python", "go")
        self.assertEqual(len(results), 0)

    def test_query_with_confidence_filter(self):
        entry = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.LOW
        )
        self.engine.ingest_knowledge(entry)
        results = self.engine.query_knowledge("java", "go", min_confidence=KnowledgeConfidence.HIGH)
        self.assertEqual(len(results), 0)

    def test_duplicate_entry_increments_usage_count(self):
        entry = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry)
        self.engine.ingest_knowledge(entry)
        self.assertEqual(self.engine.knowledge_store["k1"].usage_count, 1)

    def test_extract_pattern_from_entries(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH, success_rate=0.9
        )
        self.engine.ingest_knowledge(entry1)
        pat = self.engine.extract_pattern("java", "go", ["k1"])
        self.assertEqual(pat.source_stack, "java")
        self.assertEqual(pat.target_stack, "go")

    def test_pattern_complexity_calculation(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.UNVERIFIED
        )
        self.engine.ingest_knowledge(entry1)
        pat = self.engine.extract_pattern("java", "go", ["k1"])
        self.assertEqual(pat.complexity, "high")

    def test_predict_migration_risk(self):
        res = self.engine.predict_migration_risk("java", "go", 2000, 100)
        self.assertEqual(res.prediction_type, "risk")
        self.assertTrue(res.predicted_value > 0.1)

    def test_predict_effort(self):
        res = self.engine.predict_effort("java", "go", 2000)
        self.assertEqual(res.prediction_type, "effort")

    def test_prediction_calibration_validation(self):
        score = self.engine.validate_prediction_calibration([("p1", 10.0, 12.0)])
        self.assertAlmostEqual(score, 1.0 - (2.0/12.0))

    def test_tenant_knowledge_isolation(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH, tenant_id="t1"
        )
        self.engine.ingest_knowledge(entry1)
        res = self.engine.isolate_tenant_knowledge("t1")
        self.assertEqual(len(res), 1)
        res2 = self.engine.isolate_tenant_knowledge("t2")
        self.assertEqual(len(res2), 0)

    def test_knowledge_statistics(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry1)
        stats = self.engine.get_knowledge_stats()
        self.assertEqual(stats["total_entries"], 1)

    def test_recipe_recommendation_sorted_by_success_rate(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH, success_rate=0.9
        )
        self.engine.ingest_knowledge(entry1)
        self.engine.extract_pattern("java", "go", ["k1"])
        recs = self.engine.recommend_recipe("java", "go")
        self.assertEqual(len(recs), 1)

    def test_query_with_category_filter(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry1)
        res = self.engine.query_knowledge("java", "go", category="pattern")
        self.assertEqual(len(res), 1)
        res2 = self.engine.query_knowledge("java", "go", category="risk")
        self.assertEqual(len(res2), 0)

    def test_empty_query_returns_empty(self):
        res = self.engine.query_knowledge("java", "go")
        self.assertEqual(len(res), 0)

    def test_multi_technology_knowledge_graph(self):
        entry1 = KnowledgeEntry(
            entry_id="k1", category="pattern", source_technology="java", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        entry2 = KnowledgeEntry(
            entry_id="k2", category="pattern", source_technology="python", target_technology="go",
            title="T1", description="D1", confidence=KnowledgeConfidence.HIGH
        )
        self.engine.ingest_knowledge(entry1)
        self.engine.ingest_knowledge(entry2)
        res = self.engine.query_knowledge("java", "go")
        self.assertEqual(len(res), 1)

class TestProductLifecycleEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ProductLifecycleEngine()

    def test_api_compatibility_no_breaking(self):
        changes = [{"type": "addition", "path": "/new"}]
        res = self.engine.check_api_compatibility("rest", "1.0", "1.1", changes)
        self.assertTrue(res.backward_compatible)

    def test_api_compatibility_breaking_detected(self):
        changes = [{"type": "removal", "path": "/old"}]
        res = self.engine.check_api_compatibility("rest", "1.0", "2.0", changes)
        self.assertFalse(res.backward_compatible)

    def test_register_and_query_deprecation(self):
        d = DeprecationRecord(
            deprecation_id="d1", feature="old_api", deprecated_in="1.0",
            removal_target="2.0", migration_guide="doc"
        )
        self.engine.register_deprecation(d)
        res = self.engine.get_active_deprecations("1.5")
        self.assertEqual(len(res), 1)

    def test_active_deprecations_filtered(self):
        d = DeprecationRecord(
            deprecation_id="d1", feature="old_api", deprecated_in="1.0",
            removal_target="2.0", migration_guide="doc"
        )
        self.engine.register_deprecation(d)
        res = self.engine.get_active_deprecations("2.5")
        self.assertEqual(len(res), 0)

    def test_create_release_candidate(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        self.assertEqual(rc.overall_status, "pending")
        self.assertFalse(rc.gates_passed["test"])

    def test_update_gate_status_individual(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test", "sec"])
        self.engine.update_gate_status(rc.rc_id, "test", True)
        self.assertTrue(self.engine.release_candidates[rc.rc_id].gates_passed["test"])
        self.assertEqual(self.engine.release_candidates[rc.rc_id].overall_status, "pending")

    def test_update_gate_status_all_pass_auto_approve(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        self.engine.update_gate_status(rc.rc_id, "test", True)
        self.assertEqual(self.engine.release_candidates[rc.rc_id].overall_status, "approved")

    def test_approve_release_all_gates_passed(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        self.engine.update_gate_status(rc.rc_id, "test", True)
        res = self.engine.approve_release(rc.rc_id, "admin")
        self.assertEqual(res.overall_status, "released")
        self.assertEqual(res.approved_by, "admin")

    def test_approve_release_gates_not_passed_error(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        with self.assertRaises(ValueError):
            self.engine.approve_release(rc.rc_id, "admin")

    def test_reject_release(self):
        rc = self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        res = self.engine.reject_release(rc.rc_id, "failed tests")
        self.assertEqual(res.overall_status, "rejected")

    def test_support_policy_registration_and_lookup(self):
        p = SupportPolicy("1.0.0", ReleaseChannel.STABLE, SupportStatus.ACTIVE, "2020-01-01", "2021-01-01", "2022-01-01", "2022-01-01")
        self.engine.register_support_policy(p)
        st = self.engine.get_support_status("1.0.0")
        self.assertEqual(st, SupportStatus.ACTIVE)

    def test_eol_versions_listing(self):
        p = SupportPolicy("1.0.0", ReleaseChannel.STABLE, SupportStatus.END_OF_LIFE, "2020-01-01", "2021-01-01", "2022-01-01", "2022-01-01")
        self.engine.register_support_policy(p)
        res = self.engine.get_eol_versions()
        self.assertEqual(len(res), 1)

    def test_security_backport_eligibility(self):
        p = SupportPolicy("1.0.0", ReleaseChannel.STABLE, SupportStatus.MAINTENANCE, "2020-01-01", "2021-01-01", "2022-01-01", "2022-01-01")
        self.engine.register_support_policy(p)
        self.assertTrue(self.engine.check_security_backport_eligible("1.0.0"))

    def test_compatibility_matrix_generation(self):
        self.engine.check_api_compatibility("rest", "1.0", "2.0", [{"type": "removal"}])
        mat = self.engine.generate_compatibility_matrix(["1.0", "2.0"])
        self.assertFalse(mat[("1.0", "2.0")])

    def test_release_pipeline_status_summary(self):
        self.engine.create_release_candidate("1.0.0", ReleaseChannel.BETA, "sha123", ["test"])
        stats = self.engine.get_release_pipeline_status()
        self.assertEqual(stats["total_rcs"], 1)

if __name__ == "__main__":
    unittest.main()
