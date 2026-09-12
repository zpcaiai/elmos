import unittest
from datetime import datetime, timedelta
from elmos_mature_platform.types import (
    StoredArtifact,
    RetentionRule,
    ArtifactTier,
    RetentionPolicyAction,
)
from elmos_mature_platform.artifact_retention_economics_engine import (
    ArtifactRetentionEconomicsEngine,
)


class TestArtifactRetentionEconomicsComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ArtifactRetentionEconomicsEngine()
        self.mock_now = datetime(2026, 9, 11, 12, 0, 0)
        self.engine._mock_now = self.mock_now

    def _iso_date(self, days_ago: int) -> str:
        dt = self.mock_now - timedelta(days=days_ago)
        return dt.isoformat() + "Z"

    def test_tier_pricing_table(self):
        self.assertEqual(ArtifactRetentionEconomicsEngine.TIER_PRICING[ArtifactTier.HOT], 0.023)
        self.assertEqual(ArtifactRetentionEconomicsEngine.TIER_PRICING[ArtifactTier.WARM], 0.0125)
        self.assertEqual(ArtifactRetentionEconomicsEngine.TIER_PRICING[ArtifactTier.COLD], 0.004)
        self.assertEqual(ArtifactRetentionEconomicsEngine.TIER_PRICING[ArtifactTier.ARCHIVE], 0.001)
        self.assertEqual(ArtifactRetentionEconomicsEngine.TIER_PRICING[ArtifactTier.DELETED], 0.0)

    def test_register_artifact_defaults(self):
        artifact = StoredArtifact(
            artifact_id="art-001",
            name="build-cache.tar.gz",
            size_bytes=1024 * 1024 * 1024,
            tier=ArtifactTier.HOT,
        )
        art_id = self.engine.register_artifact(artifact)
        self.assertEqual(art_id, "art-001")
        self.assertIn("art-001", self.engine.artifacts)
        saved = self.engine.artifacts["art-001"]
        self.assertEqual(saved.cost_per_gb_month, 0.023)
        self.assertTrue(saved.created_at.endswith("Z"))
        self.assertEqual(saved.last_accessed, saved.created_at)

    def test_register_artifact_with_existing_dates_and_tier(self):
        artifact = StoredArtifact(
            artifact_id="art-002",
            name="archive-data.zip",
            size_bytes=2 * 1024 * 1024 * 1024,
            tier=ArtifactTier.COLD,
            created_at=self._iso_date(30),
            last_accessed=self._iso_date(10),
        )
        self.engine.register_artifact(artifact)
        saved = self.engine.artifacts["art-002"]
        self.assertEqual(saved.cost_per_gb_month, 0.004)
        self.assertEqual(saved.created_at, self._iso_date(30))

    def test_record_access_success(self):
        artifact = StoredArtifact(
            artifact_id="art-003",
            name="image.png",
            size_bytes=500000,
            tier=ArtifactTier.HOT,
        )
        self.engine.register_artifact(artifact)
        self.assertEqual(artifact.access_count, 0)
        updated = self.engine.record_access("art-003")
        self.assertEqual(updated.access_count, 1)
        self.assertEqual(updated.last_accessed, self.mock_now.isoformat() + "Z")

    def test_record_access_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_access("non-existent")

    def test_set_legal_hold(self):
        artifact = StoredArtifact(
            artifact_id="art-004",
            name="audit-log.json",
            size_bytes=100000,
            tier=ArtifactTier.HOT,
        )
        self.engine.register_artifact(artifact)
        self.assertFalse(artifact.legal_hold)
        res = self.engine.set_legal_hold("art-004", True)
        self.assertTrue(res.legal_hold)
        res2 = self.engine.set_legal_hold("art-004", False)
        self.assertFalse(res2.legal_hold)

    def test_set_legal_hold_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.set_legal_hold("missing", True)

    def test_create_rule(self):
        rule = RetentionRule(
            rule_id="rule-cold-90",
            name="Move to Cold after 90 days",
            max_age_days=90,
            min_access_count=0,
            action=RetentionPolicyAction.TIER_DOWN,
            target_tier=ArtifactTier.COLD,
        )
        rid = self.engine.create_rule(rule)
        self.assertEqual(rid, "rule-cold-90")
        self.assertIn("rule-cold-90", self.engine.rules)

    def test_evaluate_retention_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_retention("missing")

    def test_evaluate_retention_legal_hold(self):
        artifact = StoredArtifact(
            artifact_id="art-005",
            name="legal-evidence.pdf",
            size_bytes=1000000,
            tier=ArtifactTier.HOT,
            legal_hold=True,
            created_at=self._iso_date(365),
        )
        self.engine.register_artifact(artifact)
        rule = RetentionRule(
            rule_id="del-rule",
            name="Delete old",
            max_age_days=30,
            action=RetentionPolicyAction.DELETE,
        )
        self.engine.create_rule(rule)
        res = self.engine.evaluate_retention("art-005")
        self.assertEqual(res["action"], RetentionPolicyAction.KEEP.value)
        self.assertEqual(res["reason"], "legal_hold")
        self.assertIsNone(res["rule_id"])

    def test_evaluate_retention_matched_tier_down(self):
        artifact = StoredArtifact(
            artifact_id="art-006",
            name="old-build.tar",
            size_bytes=1024 * 1024 * 1024,
            tier=ArtifactTier.HOT,
            created_at=self._iso_date(100),
            tags={"env": "ci"},
        )
        self.engine.register_artifact(artifact)
        rule = RetentionRule(
            rule_id="rule-ci-tierdown",
            name="Tier down CI artifacts",
            max_age_days=90,
            min_access_count=0,
            action=RetentionPolicyAction.TIER_DOWN,
            target_tier=ArtifactTier.COLD,
            applies_to_tags={"env": "ci"},
        )
        self.engine.create_rule(rule)
        res = self.engine.evaluate_retention("art-006")
        self.assertEqual(res["action"], RetentionPolicyAction.TIER_DOWN.value)
        self.assertEqual(res["target_tier"], ArtifactTier.COLD.value)
        self.assertEqual(res["rule_id"], "rule-ci-tierdown")

    def test_evaluate_retention_tag_mismatch_keeps(self):
        artifact = StoredArtifact(
            artifact_id="art-007",
            name="prod-artifact.tar",
            size_bytes=1024 * 1024 * 1024,
            tier=ArtifactTier.HOT,
            created_at=self._iso_date(100),
            tags={"env": "prod"},
        )
        self.engine.register_artifact(artifact)
        rule = RetentionRule(
            rule_id="rule-ci",
            name="CI rule",
            max_age_days=30,
            action=RetentionPolicyAction.DELETE,
            applies_to_tags={"env": "ci"},
        )
        self.engine.create_rule(rule)
        res = self.engine.evaluate_retention("art-007")
        self.assertEqual(res["action"], RetentionPolicyAction.KEEP.value)
        self.assertEqual(res["reason"], "no_rule_matched")

    def test_apply_tier_change_success(self):
        artifact = StoredArtifact(
            artifact_id="art-008",
            name="dataset.parquet",
            size_bytes=1024 * 1024 * 1024,
            tier=ArtifactTier.HOT,
        )
        self.engine.register_artifact(artifact)
        updated = self.engine.apply_tier_change("art-008", ArtifactTier.ARCHIVE)
        self.assertEqual(updated.tier, ArtifactTier.ARCHIVE)
        self.assertEqual(updated.cost_per_gb_month, 0.001)

    def test_apply_tier_change_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.apply_tier_change("missing", ArtifactTier.COLD)

    def test_apply_tier_change_legal_hold_deletion_forbidden(self):
        artifact = StoredArtifact(
            artifact_id="art-009",
            name="protected.log",
            size_bytes=1000,
            tier=ArtifactTier.HOT,
            legal_hold=True,
        )
        self.engine.register_artifact(artifact)
        with self.assertRaises(PermissionError):
            self.engine.apply_tier_change("art-009", ArtifactTier.DELETED)

    def test_calculate_storage_cost(self):
        artifact = StoredArtifact(
            artifact_id="art-010",
            name="video.mp4",
            size_bytes=2 * 1024 * 1024 * 1024,
            tier=ArtifactTier.HOT,
        )
        self.engine.register_artifact(artifact)
        cost_1m = self.engine.calculate_storage_cost("art-010", months=1)
        self.assertAlmostEqual(cost_1m, 2.0 * 0.023, places=5)
        cost_3m = self.engine.calculate_storage_cost("art-010", months=3)
        self.assertAlmostEqual(cost_3m, 2.0 * 0.023 * 3, places=5)

    def test_calculate_storage_cost_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.calculate_storage_cost("missing")

    def test_get_total_cost_and_cost_by_tier(self):
        a1 = StoredArtifact("a1", "a1", 1024**3, ArtifactTier.HOT)
        a2 = StoredArtifact("a2", "a2", 2 * (1024**3), ArtifactTier.WARM)
        a3 = StoredArtifact("a3", "a3", 5 * (1024**3), ArtifactTier.COLD)
        self.engine.register_artifact(a1)
        self.engine.register_artifact(a2)
        self.engine.register_artifact(a3)

        expected_total = (1.0 * 0.023) + (2.0 * 0.0125) + (5.0 * 0.004)
        self.assertAlmostEqual(self.engine.get_total_cost(months=1), expected_total, places=5)

        by_tier = self.engine.get_cost_by_tier()
        self.assertAlmostEqual(by_tier[ArtifactTier.HOT.value], 0.023, places=5)
        self.assertAlmostEqual(by_tier[ArtifactTier.WARM.value], 0.025, places=5)
        self.assertAlmostEqual(by_tier[ArtifactTier.COLD.value], 0.020, places=5)

    def test_get_savings_opportunity(self):
        a1 = StoredArtifact(
            artifact_id="save-01",
            name="old.tar",
            size_bytes=1024**3,
            tier=ArtifactTier.HOT,
            created_at=self._iso_date(100),
        )
        self.engine.register_artifact(a1)
        rule = RetentionRule(
            rule_id="r1",
            name="Tier down to cold",
            max_age_days=60,
            action=RetentionPolicyAction.TIER_DOWN,
            target_tier=ArtifactTier.COLD,
        )
        self.engine.create_rule(rule)

        savings = self.engine.get_savings_opportunity()
        self.assertEqual(len(savings["eligible_artifacts"]), 1)
        expected_saving = 0.023 - 0.004
        self.assertAlmostEqual(savings["total_potential_savings"], expected_saving, places=5)

    def test_get_retention_report(self):
        a1 = StoredArtifact("r1", "r1", 1000, ArtifactTier.HOT, access_count=0, legal_hold=True)
        a2 = StoredArtifact("r2", "r2", 2000, ArtifactTier.COLD, access_count=5)
        a3 = StoredArtifact("r3", "r3", 3000, ArtifactTier.ARCHIVE, access_count=50)
        a4 = StoredArtifact("r4", "r4", 4000, ArtifactTier.WARM, access_count=150)
        self.engine.register_artifact(a1)
        self.engine.register_artifact(a2)
        self.engine.register_artifact(a3)
        self.engine.register_artifact(a4)

        rep = self.engine.get_retention_report()
        self.assertEqual(rep["total_artifacts"], 4)
        self.assertEqual(rep["total_size_bytes"], 10000)
        self.assertEqual(rep["legal_holds"], 1)
        self.assertEqual(rep["access_frequency"]["0"], 1)
        self.assertEqual(rep["access_frequency"]["1-10"], 1)
        self.assertEqual(rep["access_frequency"]["11-100"], 1)
        self.assertEqual(rep["access_frequency"][">100"], 1)
        self.assertEqual(rep["by_tier"]["counts"][ArtifactTier.HOT.value], 1)
        self.assertEqual(rep["by_tier"]["counts"][ArtifactTier.COLD.value], 1)


if __name__ == "__main__":
    unittest.main()
