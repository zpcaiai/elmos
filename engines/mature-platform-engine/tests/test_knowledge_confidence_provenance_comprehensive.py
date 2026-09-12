"""Comprehensive tests for KnowledgeConfidenceProvenanceEngine (Batch 41 - Skill 1405)."""

import unittest

from elmos_mature_platform.knowledge_confidence_provenance_engine import (
    KnowledgeConfidenceProvenanceEngine,
)
from elmos_mature_platform.types import (
    KnowledgeConfidenceLevel,
    KnowledgeDecayPolicy,
)


class TestKnowledgeConfidenceProvenanceComprehensive(unittest.TestCase):
    """Test suite verifying empirical knowledge confidence scoring and provenance."""

    def setUp(self):
        self.engine = KnowledgeConfidenceProvenanceEngine()

    def test_register_provenance(self):
        """Verify registering knowledge item with initial score and level."""
        rec = self.engine.register_provenance(
            knowledge_id="recipe-spring-boot-4",
            source_run_id="run-1001",
            author="sre-bot",
            initial_score=0.5,
            citations=["https://docs.spring.io"],
        )
        self.assertEqual(rec.knowledge_id, "recipe-spring-boot-4")
        self.assertEqual(rec.source_run_id, "run-1001")
        self.assertEqual(rec.confidence_score, 0.5)
        self.assertEqual(rec.confidence_level, KnowledgeConfidenceLevel.EXPERIMENTAL)
        self.assertEqual(rec.empirical_success_count, 0)
        self.assertEqual(rec.empirical_failure_count, 0)

    def test_duplicate_registration_raises_error(self):
        """Verify registering same knowledge ID twice raises ValueError."""
        self.engine.register_provenance("knowledge-dup", "run-1")
        with self.assertRaises(ValueError):
            self.engine.register_provenance("knowledge-dup", "run-2")

    def test_empirical_successes_elevate_confidence_level(self):
        """Verify repeated successes promote knowledge from EXPERIMENTAL to PRODUCTION_PROVEN to GOLD_CERTIFIED."""
        rec = self.engine.register_provenance("knowledge-transform", "run-init", initial_score=0.5)

        # 10 successes -> should reach PRODUCTION_PROVEN
        for _ in range(10):
            self.engine.record_empirical_outcome("knowledge-transform", success=True)

        rec = self.engine.get_provenance("knowledge-transform")
        self.assertIsNotNone(rec)
        self.assertEqual(rec.empirical_success_count, 10)
        self.assertEqual(rec.empirical_failure_count, 0)
        self.assertEqual(rec.confidence_level, KnowledgeConfidenceLevel.PRODUCTION_PROVEN)

        # 15 more successes (total 25) -> should reach GOLD_CERTIFIED
        for _ in range(15):
            self.engine.record_empirical_outcome("knowledge-transform", success=True)

        rec = self.engine.get_provenance("knowledge-transform")
        self.assertEqual(rec.empirical_success_count, 25)
        self.assertEqual(rec.confidence_level, KnowledgeConfidenceLevel.GOLD_CERTIFIED)

    def test_deprecate_knowledge(self):
        """Verify deprecating knowledge zeros score and prevents further outcome recording."""
        self.engine.register_provenance("knowledge-legacy", "run-leg")
        dep = self.engine.deprecate_knowledge("knowledge-legacy", reason="Migrated to v2 API")

        self.assertEqual(dep.confidence_level, KnowledgeConfidenceLevel.DEPRECATED)
        self.assertEqual(dep.confidence_score, 0.0)

        with self.assertRaises(ValueError):
            self.engine.record_empirical_outcome("knowledge-legacy", success=True)

    def test_apply_time_decay(self):
        """Verify half-life time decay reduces confidence score toward floor."""
        self.engine.register_provenance("knowledge-decay", "run-decay", initial_score=0.8)

        # After 90 days (1 half-life), score should be roughly 0.8 * 0.5 = 0.4
        decayed = self.engine.apply_time_decay("knowledge-decay", elapsed_days=90.0)
        self.assertAlmostEqual(decayed.confidence_score, 0.4, places=2)

        # Negative days raises ValueError
        with self.assertRaises(ValueError):
            self.engine.apply_time_decay("knowledge-decay", elapsed_days=-5.0)

    def test_get_provenance_chain_and_summary(self):
        """Verify audit history chain and summary aggregation across all knowledge items."""
        self.engine.register_provenance("k-1", "run-1", initial_score=0.6)
        self.engine.record_empirical_outcome("k-1", success=True)
        self.engine.record_empirical_outcome("k-1", success=False)

        chain = self.engine.get_provenance_chain("k-1")
        self.assertEqual(chain["knowledge_id"], "k-1")
        self.assertGreaterEqual(len(chain["history"]), 3)

        summary = self.engine.get_provenance_summary()
        self.assertGreaterEqual(summary["total_knowledge_assets"], 1)
        self.assertGreater(summary["average_confidence_score"], 0.0)
        self.assertEqual(summary["total_empirical_runs"], 2)


if __name__ == "__main__":
    unittest.main()
