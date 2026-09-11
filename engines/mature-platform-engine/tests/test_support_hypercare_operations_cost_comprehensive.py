"""Comprehensive test suite for SupportHypercareOperationsCostEngine (Batch 44 - Skill 1464)."""

import unittest

from elmos_mature_platform.support_hypercare_operations_cost_engine import (
    SupportHypercareOperationsCostEngine,
)
from elmos_mature_platform.types import (
    HypercarePhase,
    HypercareProjectRecord,
    SupportOperationsCostSummary,
)


class TestSupportHypercareOperationsCostComprehensive(unittest.TestCase):
    """Rigorous unit testing for SupportHypercareOperationsCostEngine."""

    def setUp(self) -> None:
        self.engine = SupportHypercareOperationsCostEngine()

    def test_register_project_success(self) -> None:
        rec = HypercareProjectRecord(
            record_id="hyp-101",
            project_id="proj-bank-core",
            customer_name="Global Bank Corp",
            phase=HypercarePhase.PRE_CUTOVER_STANDBY,
            support_tier="24x7_mission_critical",
            hypercare_duration_days=30,
            hourly_rate_usd=300.0,
            hours_logged=10.0,
        )
        rid = self.engine.register_project(rec)
        self.assertEqual(rid, "hyp-101")
        retrieved = self.engine.get_project("hyp-101")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.total_cost_usd, 3000.0)
        self.assertTrue(len(retrieved.started_at) > 0)

    def test_register_project_auto_generates_id(self) -> None:
        rec = HypercareProjectRecord(
            record_id="",
            project_id="proj-retail",
            customer_name="MegaRetail",
            hypercare_duration_days=14,
        )
        rid = self.engine.register_project(rec)
        self.assertTrue(rid.startswith("hyp-"))

    def test_register_project_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_project(
                HypercareProjectRecord("h1", "p1", "c1", hourly_rate_usd=-50.0)
            )
        with self.assertRaises(ValueError):
            self.engine.register_project(
                HypercareProjectRecord("h2", "p2", "c2", hypercare_duration_days=0)
            )

    def test_transition_phase_success(self) -> None:
        rec = HypercareProjectRecord(
            record_id="h-trans",
            project_id="p-trans",
            customer_name="TelcoX",
            phase=HypercarePhase.PRE_CUTOVER_STANDBY,
        )
        self.engine.register_project(rec)

        p1 = self.engine.transition_phase("h-trans", HypercarePhase.CUTOVER_EXECUTION)
        self.assertEqual(p1.phase, HypercarePhase.CUTOVER_EXECUTION)
        self.assertEqual(p1.concluded_at, "")

        p2 = self.engine.transition_phase("h-trans", HypercarePhase.COMPLETED)
        self.assertEqual(p2.phase, HypercarePhase.COMPLETED)
        self.assertTrue(len(p2.concluded_at) > 0)

    def test_transition_phase_unknown_project_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.transition_phase("h-ghost", HypercarePhase.COMPLETED)

    def test_log_support_hours_success(self) -> None:
        rec = HypercareProjectRecord(
            record_id="h-log",
            project_id="p-log",
            customer_name="HealthCare Inc",
            hourly_rate_usd=200.0,
        )
        self.engine.register_project(rec)

        updated = self.engine.log_support_hours("h-log", hours=25.0, escalations=2)
        self.assertEqual(updated.hours_logged, 25.0)
        self.assertEqual(updated.incident_escalation_count, 2)
        self.assertEqual(updated.total_cost_usd, 5000.0)

        # Log additional hours
        updated2 = self.engine.log_support_hours("h-log", hours=15.0, escalations=1)
        self.assertEqual(updated2.hours_logged, 40.0)
        self.assertEqual(updated2.incident_escalation_count, 3)
        self.assertEqual(updated2.total_cost_usd, 8000.0)

    def test_log_support_hours_validation_errors(self) -> None:
        rec = HypercareProjectRecord("h-err", "p", "c", hourly_rate_usd=100.0)
        self.engine.register_project(rec)

        with self.assertRaises(ValueError):
            self.engine.log_support_hours("h-err", hours=-5.0)
        with self.assertRaises(ValueError):
            self.engine.log_support_hours("h-err", hours=5.0, escalations=-1)
        with self.assertRaises(ValueError):
            self.engine.log_support_hours("h-unknown", hours=5.0)

    def test_log_support_hours_on_completed_project_raises(self) -> None:
        rec = HypercareProjectRecord(
            record_id="h-done",
            project_id="p-done",
            customer_name="DoneCorp",
            phase=HypercarePhase.COMPLETED,
        )
        self.engine.register_project(rec)
        with self.assertRaises(ValueError):
            self.engine.log_support_hours("h-done", hours=2.0)

    def test_conclude_hypercare(self) -> None:
        rec = HypercareProjectRecord("h-conc", "p", "c")
        self.engine.register_project(rec)
        concluded = self.engine.conclude_hypercare("h-conc")
        self.assertEqual(concluded.phase, HypercarePhase.COMPLETED)
        self.assertTrue(len(concluded.concluded_at) > 0)

    def test_get_project_cost(self) -> None:
        rec = HypercareProjectRecord(
            "h-cost", "p", "c", hourly_rate_usd=250.0, hours_logged=12.0
        )
        self.engine.register_project(rec)
        self.engine.log_support_hours("h-cost", hours=8.0, escalations=3)

        cost = self.engine.get_project_cost("h-cost")
        self.assertEqual(cost["hours_logged"], 20.0)
        self.assertEqual(cost["hourly_rate_usd"], 250.0)
        self.assertEqual(cost["total_cost_usd"], 5000.0)
        self.assertEqual(cost["incident_escalation_count"], 3.0)

    def test_get_operations_cost_summary(self) -> None:
        # Project 1: Standard tier, active, 10h @ $200 = $2000
        self.engine.register_project(
            HypercareProjectRecord(
                "p1", "proj1", "Cust1", support_tier="standard", hourly_rate_usd=200.0, hours_logged=10.0
            )
        )
        # Project 2: Premium tier, active, 20h @ $300 = $6000
        self.engine.register_project(
            HypercareProjectRecord(
                "p2", "proj2", "Cust2", support_tier="premium", hourly_rate_usd=300.0, hours_logged=20.0
            )
        )
        # Project 3: Standard tier, completed, 15h @ $200 = $3000
        p3 = HypercareProjectRecord(
            "p3", "proj3", "Cust3", support_tier="standard", hourly_rate_usd=200.0, hours_logged=15.0
        )
        self.engine.register_project(p3)
        self.engine.conclude_hypercare("p3")

        summary = self.engine.get_operations_cost_summary()
        self.assertEqual(summary.total_projects_count, 3)
        self.assertEqual(summary.active_hypercare_count, 2)
        self.assertEqual(summary.total_hours_logged, 45.0)
        self.assertEqual(summary.total_support_cost_usd, 11000.0)
        self.assertAlmostEqual(summary.average_cost_per_project_usd, 11000.0 / 3, places=2)
        self.assertEqual(summary.by_support_tier["standard"], 5000.0)
        self.assertEqual(summary.by_support_tier["premium"], 6000.0)

    def test_get_hypercare_report(self) -> None:
        self.engine.register_project(
            HypercareProjectRecord(
                "p-rep", "pr", "Cust", hourly_rate_usd=100.0, hours_logged=10.0, incident_escalation_count=2
            )
        )
        report = self.engine.get_hypercare_report()
        self.assertEqual(report["total_projects"], 1)
        self.assertEqual(report["total_incident_escalations"], 2)
        self.assertIn("projects_by_phase", report)


if __name__ == "__main__":
    unittest.main()
