"""Comprehensive tests for OncallFollowTheSunEngine (Batch 39 - Skill 1358)."""

import unittest

from elmos_mature_platform.oncall_follow_the_sun_engine import (
    OncallFollowTheSunEngine,
)
from elmos_mature_platform.types import (
    HandoverStatus,
    SunRegion,
)


class TestOncallFollowTheSunComprehensive(unittest.TestCase):
    """Test suite verifying 24/7 Follow-the-Sun on-call scheduling and shift handovers."""

    def setUp(self):
        self.engine = OncallFollowTheSunEngine()
        self.schedule = self.engine.create_schedule(
            date="2026-09-11",
            apac_engineer="engineer-tokyo",
            emea_engineer="engineer-london",
            amer_engineer="engineer-seattle",
        )

    def test_create_schedule(self):
        """Verify schedule creation with full 3-region coverage."""
        self.assertTrue(self.schedule.schedule_id.startswith("fts-2026-09-11"))
        self.assertEqual(self.schedule.region_shifts[SunRegion.APAC.value], "engineer-tokyo")
        self.assertEqual(self.schedule.region_shifts[SunRegion.EMEA.value], "engineer-london")
        self.assertEqual(self.schedule.region_shifts[SunRegion.AMER.value], "engineer-seattle")

    def test_missing_engineer_raises_error(self):
        """Verify empty engineer name raises ValueError."""
        with self.assertRaises(ValueError):
            self.engine.create_schedule("2026-09-12", "", "emea-lead", "amer-lead")

    def test_get_active_region_for_utc_hour(self):
        """Verify UTC hour mappings to sun regions."""
        self.assertEqual(self.engine.get_active_region_for_utc_hour(3), SunRegion.APAC)
        self.assertEqual(self.engine.get_active_region_for_utc_hour(10), SunRegion.EMEA)
        self.assertEqual(self.engine.get_active_region_for_utc_hour(18), SunRegion.AMER)

        with self.assertRaises(ValueError):
            self.engine.get_active_region_for_utc_hour(24)

    def test_initiate_handover_rotation(self):
        """Verify handover sets outgoing and incoming engineers based on sun rotation."""
        # APAC -> EMEA
        h1 = self.engine.initiate_handover(
            self.schedule.schedule_id,
            outgoing_region=SunRegion.APAC,
            active_incidents=["INC-101"],
            watch_items=["Kafka lag spike"],
            notes="DB failover tested cleanly",
        )
        self.assertEqual(h1.outgoing_region, SunRegion.APAC)
        self.assertEqual(h1.incoming_region, SunRegion.EMEA)
        self.assertEqual(h1.outgoing_engineer, "engineer-tokyo")
        self.assertEqual(h1.incoming_engineer, "engineer-london")
        self.assertEqual(h1.status, HandoverStatus.SCHEDULED)
        self.assertEqual(h1.active_incidents, ["INC-101"])

    def test_complete_handover_lifecycle(self):
        """Verify lifecycle: SCHEDULED -> IN_PROGRESS -> COMPLETED with engineer check."""
        h = self.engine.initiate_handover(
            self.schedule.schedule_id,
            outgoing_region=SunRegion.EMEA,
            active_incidents=[],
            watch_items=[],
        )
        # Transition to IN_PROGRESS
        self.engine.start_handover(h.handover_id)
        self.assertEqual(h.status, HandoverStatus.IN_PROGRESS)

        # Mismatched incoming engineer raises ValueError
        with self.assertRaises(ValueError):
            self.engine.acknowledge_and_complete_handover(h.handover_id, incoming_engineer="wrong-engineer")

        # Correct incoming engineer completes transfer
        completed = self.engine.acknowledge_and_complete_handover(
            h.handover_id,
            incoming_engineer="engineer-seattle",
        )
        self.assertEqual(completed.status, HandoverStatus.COMPLETED)
        self.assertTrue(len(completed.acknowledged_at) > 0)

    def test_mark_missed_handover(self):
        """Verify marking handover as missed with reason."""
        h = self.engine.initiate_handover(self.schedule.schedule_id, SunRegion.AMER, [], [])
        missed = self.engine.mark_missed(h.handover_id, reason="No acknowledgment after 30m SLA")
        self.assertEqual(missed.status, HandoverStatus.MISSED)
        self.assertIn("MISSED", missed.notes)

    def test_get_current_oncall_and_handover_report(self):
        """Verify current on-call lookup and handover aggregate reporting."""
        current = self.engine.get_current_oncall(self.schedule.schedule_id, utc_hour=12)
        self.assertEqual(current["active_region"], SunRegion.EMEA.value)
        self.assertEqual(current["oncall_engineer"], "engineer-london")

        report = self.engine.get_handover_report(self.schedule.schedule_id)
        self.assertEqual(report["schedule_id"], self.schedule.schedule_id)
        self.assertIn("total_handovers", report)


if __name__ == "__main__":
    unittest.main()
