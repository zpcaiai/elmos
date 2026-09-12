"""Comprehensive test suite for CustomerStatusCommunicationEngine (B39 - Skill 1357)."""

import unittest

from elmos_mature_platform.customer_status_communication_engine import (
    CustomerStatusCommunicationEngine,
)
from elmos_mature_platform.types import (
    IncidentImpactLevel,
    NotificationChannel,
)


class TestCustomerStatusCommunicationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = CustomerStatusCommunicationEngine(initial_uptime_pct=99.98)

    def test_initial_status_page_report_clean(self):
        report = self.engine.get_status_page_report()
        self.assertEqual(report.active_incidents_count, 0)
        self.assertEqual(report.current_global_status, IncidentImpactLevel.NONE)
        self.assertEqual(report.past_30_days_uptime_pct, 99.98)
        self.assertEqual(len(report.messages), 0)

    def test_broadcast_incident_update_elevates_global_status(self):
        msg = self.engine.broadcast_incident_update(
            incident_id="INC-4041",
            impact_level=IncidentImpactLevel.MAJOR,
            title="Database Latency Spike in EU Region",
            body="Investigating replication latency impacting read operations",
            affected_components=["api-gateway", "database-replica"],
            channels=[NotificationChannel.STATUS_PAGE, NotificationChannel.EMAIL_PAGER],
        )
        self.assertIsNotNone(msg)
        self.assertEqual(msg.incident_id, "INC-4041")

        report = self.engine.get_status_page_report()
        self.assertEqual(report.active_incidents_count, 1)
        self.assertEqual(report.current_global_status, IncidentImpactLevel.MAJOR)
        self.assertEqual(len(report.messages), 1)

    def test_critical_incident_overrides_major_global_status(self):
        self.engine.broadcast_incident_update("INC-1", IncidentImpactLevel.MINOR, "Minor glitch", "details", ["cache"])
        self.engine.broadcast_incident_update("INC-2", IncidentImpactLevel.CRITICAL, "Full Outage", "investigating", ["core-api"])

        report = self.engine.get_status_page_report()
        self.assertEqual(report.active_incidents_count, 2)
        self.assertEqual(report.current_global_status, IncidentImpactLevel.CRITICAL)

    def test_incident_timeline_chronological_ordering(self):
        self.engine.broadcast_incident_update("INC-TIMELINE", IncidentImpactLevel.MAJOR, "Step 1: Investigating", "looking into it", ["auth"])
        self.engine.broadcast_incident_update("INC-TIMELINE", IncidentImpactLevel.MAJOR, "Step 2: Identified", "memory leak found", ["auth"])
        self.engine.broadcast_incident_update("INC-TIMELINE", IncidentImpactLevel.MINOR, "Step 3: Monitoring", "fix applied, verifying", ["auth"])

        timeline = self.engine.get_incident_timeline("INC-TIMELINE")
        self.assertEqual(len(timeline), 3)
        self.assertIn("Step 1", timeline[0].title)
        self.assertIn("Step 2", timeline[1].title)
        self.assertIn("Step 3", timeline[2].title)

    def test_resolve_incident_communication(self):
        self.engine.broadcast_incident_update("INC-RES", IncidentImpactLevel.CRITICAL, "Critical Issue", "details", ["db"])
        report1 = self.engine.get_status_page_report()
        self.assertEqual(report1.active_incidents_count, 1)

        # Resolve
        resolve_msg = self.engine.resolve_incident_communication(
            incident_id="INC-RES",
            resolution_notes="Root cause remediated. All systems operating normally.",
            affected_components=["db"],
        )
        self.assertEqual(resolve_msg.impact_level, IncidentImpactLevel.NONE)

        report2 = self.engine.get_status_page_report()
        self.assertEqual(report2.active_incidents_count, 0)
        self.assertEqual(report2.current_global_status, IncidentImpactLevel.NONE)

    def test_update_30_day_uptime(self):
        self.engine.update_30_day_uptime(99.995)
        rep = self.engine.get_status_page_report()
        self.assertEqual(rep.past_30_days_uptime_pct, 99.995)

    def test_update_uptime_invalid_percentage_raises(self):
        with self.assertRaises(ValueError):
            self.engine.update_30_day_uptime(105.0)


if __name__ == "__main__":
    unittest.main()
