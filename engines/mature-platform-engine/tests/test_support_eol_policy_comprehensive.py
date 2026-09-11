"""Comprehensive test suite for SupportEolPolicyEngine (Batch 43 - Skill 1445)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.support_eol_policy_engine import SupportEolPolicyEngine
from elmos_mature_platform.types import (
    EolLifecyclePhase,
    ProductReleaseLifecycle,
)


class TestSupportEolPolicyComprehensive(unittest.TestCase):
    """Rigorous unit testing for SupportEolPolicyEngine."""

    def setUp(self) -> None:
        self.engine = SupportEolPolicyEngine()

    def test_register_release_lifecycle_success(self) -> None:
        lc = ProductReleaseLifecycle(
            release_id="rel-v1",
            product_name="Elmos Gateway",
            version="1.0.0",
            ga_date="2025-01-01",
            active_support_end_date="2026-01-01",
            maintenance_support_end_date="2027-01-01",
            eol_date="2028-01-01",
            extended_support_available=True,
        )
        rid = self.engine.register_release_lifecycle(lc)
        self.assertEqual(rid, "rel-v1")

    def test_register_release_lifecycle_auto_generates_id(self) -> None:
        lc = ProductReleaseLifecycle(
            release_id="",
            product_name="Elmos Broker",
            version="2.0.0",
            ga_date="2025-06-01",
            active_support_end_date="2026-06-01",
            maintenance_support_end_date="2027-06-01",
            eol_date="2028-06-01",
        )
        rid = self.engine.register_release_lifecycle(lc)
        self.assertTrue(rid.startswith("rel-life-"))

    def test_register_missing_required_fields_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_release_lifecycle(
                ProductReleaseLifecycle(release_id="1", product_name="", version="1.0", ga_date="2025-01-01", active_support_end_date="", maintenance_support_end_date="", eol_date="2026-01-01")
            )
        with self.assertRaises(ValueError):
            self.engine.register_release_lifecycle(
                ProductReleaseLifecycle(release_id="2", product_name="P", version="", ga_date="2025-01-01", active_support_end_date="", maintenance_support_end_date="", eol_date="2026-01-01")
            )
        with self.assertRaises(ValueError):
            self.engine.register_release_lifecycle(
                ProductReleaseLifecycle(release_id="3", product_name="P", version="1.0", ga_date="", active_support_end_date="", maintenance_support_end_date="", eol_date="2026-01-01")
            )
        with self.assertRaises(ValueError):
            self.engine.register_release_lifecycle(
                ProductReleaseLifecycle(release_id="4", product_name="P", version="1.0", ga_date="2025-01-01", active_support_end_date="", maintenance_support_end_date="", eol_date="")
            )

    def test_evaluate_phase_transitions(self) -> None:
        lc = ProductReleaseLifecycle(
            release_id="rel-phases",
            product_name="Elmos Core",
            version="1.0",
            ga_date="2024-01-01",
            active_support_end_date="2025-01-01",
            maintenance_support_end_date="2026-01-01",
            eol_date="2027-01-01",
            extended_support_available=True,
        )
        self.engine.register_release_lifecycle(lc)

        # Before active support end
        p1 = self.engine.evaluate_phase("rel-phases", as_of_date="2024-06-01")
        self.assertEqual(p1, EolLifecyclePhase.ACTIVE_SUPPORT)
        self.assertFalse(lc.critical_security_fixes_only)

        # In maintenance support
        p2 = self.engine.evaluate_phase("rel-phases", as_of_date="2025-06-01")
        self.assertEqual(p2, EolLifecyclePhase.MAINTENANCE_SUPPORT)
        self.assertTrue(lc.critical_security_fixes_only)

        # In extended support (since extended_support_available is True)
        p3 = self.engine.evaluate_phase("rel-phases", as_of_date="2026-06-01")
        self.assertEqual(p3, EolLifecyclePhase.EXTENDED_SUPPORT)
        self.assertTrue(lc.critical_security_fixes_only)

        # Past EOL date
        p4 = self.engine.evaluate_phase("rel-phases", as_of_date="2027-06-01")
        self.assertEqual(p4, EolLifecyclePhase.END_OF_LIFE)
        self.assertFalse(lc.critical_security_fixes_only)

    def test_evaluate_phase_without_extended_support(self) -> None:
        lc = ProductReleaseLifecycle(
            release_id="rel-no-ext",
            product_name="Elmos Fast",
            version="1.0",
            ga_date="2024-01-01",
            active_support_end_date="2025-01-01",
            maintenance_support_end_date="2026-01-01",
            eol_date="2027-01-01",
            extended_support_available=False,
        )
        self.engine.register_release_lifecycle(lc)

        # Past maintenance support end date -> END_OF_LIFE
        p = self.engine.evaluate_phase("rel-no-ext", as_of_date="2026-06-01")
        self.assertEqual(p, EolLifecyclePhase.END_OF_LIFE)

    def test_evaluate_phase_missing_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.evaluate_phase("unknown-rel")

    def test_feature_and_security_patch_eligibility(self) -> None:
        lc = ProductReleaseLifecycle(
            release_id="rel-elig",
            product_name="Elmos Test",
            version="2.0",
            ga_date="2025-01-01",
            active_support_end_date="2026-01-01",
            maintenance_support_end_date="2027-01-01",
            eol_date="2028-01-01",
            extended_support_available=True,
        )
        self.engine.register_release_lifecycle(lc)

        # Active support period
        self.assertEqual(self.engine.evaluate_phase("rel-elig", as_of_date="2025-06-01"), EolLifecyclePhase.ACTIVE_SUPPORT)
        self.assertTrue(self.engine.can_receive_feature_update("rel-elig", as_of_date="2025-06-01"))
        self.assertTrue(self.engine.can_receive_security_patch("rel-elig", as_of_date="2025-06-01"))

        # Maintenance support period
        self.assertEqual(self.engine.evaluate_phase("rel-elig", as_of_date="2026-06-01"), EolLifecyclePhase.MAINTENANCE_SUPPORT)
        self.assertFalse(self.engine.can_receive_feature_update("rel-elig", as_of_date="2026-06-01"))
        self.assertTrue(self.engine.can_receive_security_patch("rel-elig", as_of_date="2026-06-01"))

        # EOL period
        self.assertEqual(self.engine.evaluate_phase("rel-elig", as_of_date="2029-01-01"), EolLifecyclePhase.END_OF_LIFE)
        self.assertFalse(self.engine.can_receive_feature_update("rel-elig", as_of_date="2029-01-01"))
        self.assertFalse(self.engine.can_receive_security_patch("rel-elig", as_of_date="2029-01-01"))

    def test_get_eol_roadmap(self) -> None:
        lc1 = ProductReleaseLifecycle(
            release_id="r1", product_name="Elmos A", version="1.0",
            ga_date="2024-01-01", active_support_end_date="2025-01-01",
            maintenance_support_end_date="2026-01-01", eol_date="2027-01-01",
        )
        lc2 = ProductReleaseLifecycle(
            release_id="r2", product_name="Elmos B", version="1.0",
            ga_date="2023-01-01", active_support_end_date="2024-01-01",
            maintenance_support_end_date="2025-01-01", eol_date="2026-01-01",
        )
        self.engine.register_release_lifecycle(lc1)
        self.engine.register_release_lifecycle(lc2)

        roadmap = self.engine.get_eol_roadmap()
        self.assertEqual(len(roadmap), 2)
        # Should be sorted by eol_date: r2 (2026) before r1 (2027)
        self.assertEqual(roadmap[0].release_id, "r2")
        self.assertEqual(roadmap[1].release_id, "r1")

        filtered = self.engine.get_eol_roadmap(product_name="Elmos A")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].release_id, "r1")

    def test_get_lifecycle_report(self) -> None:
        rep_empty = self.engine.get_lifecycle_report()
        self.assertEqual(rep_empty["total_tracked_releases"], 0)
        self.assertEqual(rep_empty["eol_releases_count"], 0)

        lc = ProductReleaseLifecycle(
            release_id="r-eol", product_name="Old", version="0.1",
            ga_date="2020-01-01", active_support_end_date="2021-01-01",
            maintenance_support_end_date="2022-01-01", eol_date="2023-01-01",
        )
        self.engine.register_release_lifecycle(lc)

        rep = self.engine.get_lifecycle_report()
        self.assertEqual(rep["total_tracked_releases"], 1)
        self.assertEqual(rep["eol_releases_count"], 1)


if __name__ == "__main__":
    unittest.main()
