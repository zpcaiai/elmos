"""Comprehensive unit tests for SemanticBehaviorCertificationEngine (Batch 45 Skill 1479)."""

import unittest

from elmos_mature_platform.semantic_behavior_certification_engine import (
    SemanticBehaviorCertificationEngine,
)
from elmos_mature_platform.types import (
    SemanticEquivalenceTier,
    DifferentialBehaviorDimension,
    SemanticBehaviorAssertionResult,
    SemanticBehaviorCertificationRecord,
)


class TestSemanticBehaviorCertificationComprehensive(unittest.TestCase):
    """Test suite for differential semantic behavior certification across migrated systems."""

    def setUp(self) -> None:
        self.engine = SemanticBehaviorCertificationEngine()
        self.cert_record = self.engine.create_certification_record(
            source_system_ref="legacy-order-service-v1",
            target_system_ref="modern-order-service-v2",
            min_assertions=5,
        )

    def _populate_assertions(self, payload_ok: bool = True, side_effect_ok: bool = True) -> None:
        """Helper to inject 5 assertions covering differential dimensions."""
        dimensions = [
            (DifferentialBehaviorDimension.OUTPUT_PAYLOAD, "Payload Equivalence", payload_ok),
            (DifferentialBehaviorDimension.SIDE_EFFECT, "DB Transaction & Ledger Invariants", side_effect_ok),
            (DifferentialBehaviorDimension.LATENCY_PROFILE, "P99 Response Time Boundary", True),
            (DifferentialBehaviorDimension.ERROR_RECOVERY, "Circuit Breaker Fallback State", True),
            (DifferentialBehaviorDimension.EVENT_STREAM, "Kafka Event Schema & Ordering", True),
        ]
        for idx, (dim, name, ok) in enumerate(dimensions):
            assertion = SemanticBehaviorAssertionResult(
                assertion_id=f"ast-{idx}",
                dimension=dim,
                name=name,
                equivalent=ok,
            )
            self.engine.record_assertion(self.cert_record.cert_id, assertion)

    def test_create_certification_record(self) -> None:
        rec = self.engine.get_record(self.cert_record.cert_id)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.tier, SemanticEquivalenceTier.NON_EQUIVALENT)
        self.assertFalse(rec.is_certified)

    def test_evaluate_insufficient_assertions(self) -> None:
        # Record only 2 assertions when 5 are required
        a1 = SemanticBehaviorAssertionResult(
            assertion_id="a1",
            dimension=DifferentialBehaviorDimension.OUTPUT_PAYLOAD,
            name="Output check",
            equivalent=True,
        )
        self.engine.record_assertion(self.cert_record.cert_id, a1)
        evaluated = self.engine.evaluate_equivalence(self.cert_record.cert_id)
        self.assertEqual(evaluated.tier, SemanticEquivalenceTier.NON_EQUIVALENT)
        self.assertFalse(evaluated.is_certified)

    def test_evaluate_strict_equivalence_passes(self) -> None:
        self._populate_assertions(payload_ok=True, side_effect_ok=True)
        evaluated = self.engine.evaluate_equivalence(self.cert_record.cert_id)
        self.assertEqual(evaluated.tier, SemanticEquivalenceTier.STRICT_EQUIVALENT)
        self.assertTrue(evaluated.is_certified)

    def test_evaluate_payload_failure_blocks_certification(self) -> None:
        self._populate_assertions(payload_ok=False, side_effect_ok=True)
        evaluated = self.engine.evaluate_equivalence(self.cert_record.cert_id)
        self.assertEqual(evaluated.tier, SemanticEquivalenceTier.NON_EQUIVALENT)
        self.assertFalse(evaluated.is_certified)

    def test_evaluate_side_effect_failure_blocks_certification(self) -> None:
        self._populate_assertions(payload_ok=True, side_effect_ok=False)
        evaluated = self.engine.evaluate_equivalence(self.cert_record.cert_id)
        self.assertEqual(evaluated.tier, SemanticEquivalenceTier.NON_EQUIVALENT)
        self.assertFalse(evaluated.is_certified)

    def test_issue_certification_attestation(self) -> None:
        # Fails before evaluation / when uncertified
        with self.assertRaises(ValueError):
            self.engine.issue_certification(self.cert_record.cert_id, "cert-authority-01")

        self._populate_assertions(payload_ok=True, side_effect_ok=True)
        certified = self.engine.issue_certification(self.cert_record.cert_id, "cert-authority-01")
        self.assertTrue(certified.is_certified)
        self.assertEqual(certified.certified_by, "cert-authority-01")
        self.assertTrue(certified.certified_at)

    def test_dimension_summary_and_reporting(self) -> None:
        self._populate_assertions(payload_ok=True, side_effect_ok=True)
        summary = self.engine.get_dimension_summary(self.cert_record.cert_id)
        self.assertEqual(summary["output_payload"]["equivalent"], 1)
        self.assertEqual(summary["output_payload"]["divergent"], 0)

        report = self.engine.get_certification_report()
        self.assertEqual(report["total_certifications"], 1)


if __name__ == "__main__":
    unittest.main()
