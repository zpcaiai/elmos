"""Comprehensive test suite for MaturityModelEditionsEngine (Batch 45 - Skill 1476)."""

import unittest

from elmos_mature_platform.maturity_model_editions_engine import MaturityModelEditionsEngine
from elmos_mature_platform.types import (
    EditionMaturityProfile,
    MaturityGapAssessment,
    PlatformMaturityLevel,
)


class TestMaturityModelEditionsComprehensive(unittest.TestCase):
    """Rigorous unit testing for MaturityModelEditionsEngine."""

    def setUp(self) -> None:
        self.engine = MaturityModelEditionsEngine()

    def test_register_edition_profile_success(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-airgap",
            edition="air-gapped",
            current_level=PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
            target_level=PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY,
        )
        pid = self.engine.register_edition_profile(prof)
        self.assertEqual(pid, "prof-airgap")
        retrieved = self.engine.get_profile("prof-airgap")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.edition, "air-gapped")
        self.assertTrue(len(retrieved.capabilities_pending) > 0)
        self.assertTrue(len(retrieved.last_audited) > 0)

    def test_register_edition_profile_auto_generates_id(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="",
            edition="saas",
            current_level=PlatformMaturityLevel.LEVEL_2_RELIABLE,
            target_level=PlatformMaturityLevel.LEVEL_4_HIGH_ASSURANCE,
        )
        pid = self.engine.register_edition_profile(prof)
        self.assertTrue(pid.startswith("matprof-"))

    def test_register_edition_profile_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_edition_profile(
                EditionMaturityProfile(
                    "p1",
                    "",
                    PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
                    PlatformMaturityLevel.LEVEL_2_RELIABLE,
                )
            )

    def test_fulfill_capability_success(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-ful",
            edition="sovereign",
            current_level=PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
            target_level=PlatformMaturityLevel.LEVEL_2_RELIABLE,
            capabilities_pending=["reproducible_build", "basic_telemetry"],
        )
        self.engine.register_edition_profile(prof)

        updated = self.engine.fulfill_capability("prof-ful", "reproducible_build")
        self.assertNotIn("reproducible_build", updated.capabilities_pending)
        self.assertIn("reproducible_build", updated.capabilities_fulfilled)

        # Fulfill external capability
        updated2 = self.engine.fulfill_capability("prof-ful", "custom_security_scan")
        self.assertIn("custom_security_scan", updated2.capabilities_fulfilled)

    def test_fulfill_capability_unknown_profile_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.fulfill_capability("prof-ghost", "cap")

    def test_promote_maturity_level_success(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-prom",
            edition="vpc",
            current_level=PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
            target_level=PlatformMaturityLevel.LEVEL_2_RELIABLE,
            capabilities_pending=["cap_a"],
        )
        self.engine.register_edition_profile(prof)
        self.engine.fulfill_capability("prof-prom", "cap_a")

        promoted = self.engine.promote_maturity_level(
            "prof-prom", PlatformMaturityLevel.LEVEL_2_RELIABLE
        )
        self.assertEqual(promoted.current_level, PlatformMaturityLevel.LEVEL_2_RELIABLE)
        self.assertEqual(promoted.target_level, PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY)
        # Should now have Level 3 requirements in pending
        self.assertIn("multi_tenant_isolation", promoted.capabilities_pending)

    def test_promote_fails_with_pending_capabilities(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-pend",
            edition="on-prem",
            current_level=PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
            target_level=PlatformMaturityLevel.LEVEL_2_RELIABLE,
            capabilities_pending=["unfulfilled_gate"],
        )
        self.engine.register_edition_profile(prof)

        with self.assertRaises(ValueError):
            self.engine.promote_maturity_level("prof-pend", PlatformMaturityLevel.LEVEL_2_RELIABLE)

    def test_promote_fails_to_lower_or_equal_level(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-low",
            edition="test-ed",
            current_level=PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY,
            target_level=PlatformMaturityLevel.LEVEL_4_HIGH_ASSURANCE,
            capabilities_pending=[],
        )
        self.engine.register_edition_profile(prof)

        with self.assertRaises(ValueError):
            self.engine.promote_maturity_level("prof-low", PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY)
        with self.assertRaises(ValueError):
            self.engine.promote_maturity_level("prof-low", PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL)

    def test_assess_maturity_gap(self) -> None:
        prof = EditionMaturityProfile(
            profile_id="prof-gap",
            edition="customer-dedicated",
            current_level=PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
            target_level=PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY,
            capabilities_fulfilled=["reproducible_build"],
            capabilities_pending=["basic_telemetry"],
        )
        self.engine.register_edition_profile(prof)

        gap = self.engine.assess_maturity_gap(
            "customer-dedicated", PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY
        )
        self.assertEqual(gap.edition, "customer-dedicated")
        self.assertEqual(gap.from_level, PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL)
        self.assertEqual(gap.to_level, PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY)
        self.assertTrue(len(gap.gap_capabilities) > 0)
        self.assertIn("multi_tenant_isolation", gap.gap_capabilities)
        self.assertIn("basic_telemetry", gap.gap_capabilities)
        self.assertTrue(gap.estimated_remediation_weeks >= 4)

    def test_assess_maturity_gap_unknown_edition_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.assess_maturity_gap("alien-cloud", PlatformMaturityLevel.LEVEL_5_AUTONOMOUS_ENTERPRISE)

    def test_get_maturity_report(self) -> None:
        self.engine.register_edition_profile(
            EditionMaturityProfile(
                "p1",
                "air-gapped",
                PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL,
                PlatformMaturityLevel.LEVEL_2_RELIABLE,
                capabilities_fulfilled=["cap1", "cap2"],
                capabilities_pending=["cap3"],
            )
        )
        self.engine.register_edition_profile(
            EditionMaturityProfile(
                "p2",
                "saas",
                PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY,
                PlatformMaturityLevel.LEVEL_4_HIGH_ASSURANCE,
                capabilities_fulfilled=["cap4"],
                capabilities_pending=[],
            )
        )

        report = self.engine.get_maturity_report()
        self.assertEqual(report["total_editions_profiled"], 2)
        self.assertEqual(report["distribution_by_level"][PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL.value], 1)
        self.assertEqual(report["distribution_by_level"][PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY.value], 1)
        self.assertEqual(report["total_capabilities_fulfilled"], 3)
        self.assertEqual(report["total_capabilities_pending"], 1)
        self.assertEqual(report["average_fulfilled_per_edition"], 1.5)


if __name__ == "__main__":
    unittest.main()
