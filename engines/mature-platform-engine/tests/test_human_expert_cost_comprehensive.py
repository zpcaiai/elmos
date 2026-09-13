"""Comprehensive test suite for HumanExpertCostEngine (Batch 44 - Skill 1463)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.human_expert_cost_engine import HumanExpertCostEngine
from elmos_mature_platform.types import (
    ExpertRoleTier,
    HumanCostSummary,
    HumanExpertEngagement,
)


class TestHumanExpertCostComprehensive(unittest.TestCase):
    """Rigorous unit testing for HumanExpertCostEngine."""

    def setUp(self) -> None:
        self.engine = HumanExpertCostEngine()

    def test_register_engagement_success(self) -> None:
        eng = HumanExpertEngagement(
            engagement_id="eng-arch-1",
            project_id="proj-legacy-core",
            role_tier=ExpertRoleTier.DISTINGUISHED_ARCHITECT,
            hourly_rate_usd=350.0,
            active=True,
        )
        eid = self.engine.register_engagement(eng)
        self.assertEqual(eid, "eng-arch-1")
        fetched = self.engine.get_engagement("eng-arch-1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.role_tier, ExpertRoleTier.DISTINGUISHED_ARCHITECT)
        self.assertEqual(fetched.hourly_rate_usd, 350.0)

    def test_register_engagement_auto_generates_id_and_date(self) -> None:
        eng = HumanExpertEngagement(
            engagement_id="",
            project_id="proj-spring-boot",
            role_tier=ExpertRoleTier.SENIOR_MIGRATION_ENGINEER,
            hourly_rate_usd=220.0,
        )
        eid = self.engine.register_engagement(eng)
        self.assertTrue(eid.startswith("eng-"))
        self.assertTrue(len(eng.assigned_at) > 0)

    def test_register_engagement_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_engagement(
                HumanExpertEngagement("1", "", ExpertRoleTier.QA_AUTOMATION_SPECIALIST, 150.0)
            )
        with self.assertRaises(ValueError):
            self.engine.register_engagement(
                HumanExpertEngagement("2", "proj", ExpertRoleTier.QA_AUTOMATION_SPECIALIST, -10.0)
            )

    def test_log_hours_billable_and_non_billable(self) -> None:
        eng = HumanExpertEngagement(
            engagement_id="eng-log",
            project_id="p1",
            role_tier=ExpertRoleTier.DOMAIN_SECURITY_EXPERT,
            hourly_rate_usd=300.0,
        )
        self.engine.register_engagement(eng)

        # 10 billable hours
        self.engine.log_hours("eng-log", 10.0, is_billable=True, task_id="TASK-SEC-01")
        self.assertEqual(eng.hours_logged, 10.0)
        self.assertEqual(eng.billable_hours, 10.0)
        self.assertIn("TASK-SEC-01", eng.tasks_addressed)

        # 5 non-billable hours
        self.engine.log_hours("eng-log", 5.0, is_billable=False, task_id="TASK-INTERNAL-TRAIN")
        self.assertEqual(eng.hours_logged, 15.0)
        self.assertEqual(eng.billable_hours, 10.0)
        self.assertEqual(len(eng.tasks_addressed), 2)

    def test_log_hours_inactive_engagement_raises(self) -> None:
        eng = HumanExpertEngagement(
            engagement_id="eng-closed",
            project_id="p1",
            role_tier=ExpertRoleTier.QA_AUTOMATION_SPECIALIST,
            hourly_rate_usd=150.0,
            active=False,
        )
        self.engine.register_engagement(eng)
        with self.assertRaises(ValueError) as ctx:
            self.engine.log_hours("eng-closed", 4.0)
        self.assertIn("closed", str(ctx.exception))

    def test_log_hours_invalid_hours_raises(self) -> None:
        eng = HumanExpertEngagement("eng-inv", "p1", ExpertRoleTier.SENIOR_MIGRATION_ENGINEER, 200.0)
        self.engine.register_engagement(eng)
        with self.assertRaises(ValueError):
            self.engine.log_hours("eng-inv", 0.0)
        with self.assertRaises(ValueError):
            self.engine.log_hours("eng-inv", -5.0)

    def test_calculate_engagement_cost(self) -> None:
        eng = HumanExpertEngagement(
            engagement_id="eng-calc",
            project_id="p1",
            role_tier=ExpertRoleTier.DISTINGUISHED_ARCHITECT,
            hourly_rate_usd=400.0,
        )
        self.engine.register_engagement(eng)
        self.engine.log_hours("eng-calc", 20.0, is_billable=True)
        self.engine.log_hours("eng-calc", 5.0, is_billable=False)

        cost_info = self.engine.calculate_engagement_cost("eng-calc")
        self.assertEqual(cost_info["hours_logged"], 25.0)
        self.assertEqual(cost_info["billable_hours"], 20.0)
        self.assertEqual(cost_info["total_cost_usd"], 10000.0)
        self.assertEqual(cost_info["billable_cost_usd"], 8000.0)

    def test_get_cost_by_role(self) -> None:
        e1 = HumanExpertEngagement("e1", "p1", ExpertRoleTier.QA_AUTOMATION_SPECIALIST, 150.0)
        e2 = HumanExpertEngagement("e2", "p2", ExpertRoleTier.QA_AUTOMATION_SPECIALIST, 150.0)
        e3 = HumanExpertEngagement("e3", "p3", ExpertRoleTier.DISTINGUISHED_ARCHITECT, 400.0)
        self.engine.register_engagement(e1)
        self.engine.register_engagement(e2)
        self.engine.register_engagement(e3)

        self.engine.log_hours("e1", 10.0)  # 1500
        self.engine.log_hours("e2", 20.0)  # 3000
        self.engine.log_hours("e3", 5.0)   # 2000

        qa_cost = self.engine.get_cost_by_role(ExpertRoleTier.QA_AUTOMATION_SPECIALIST)
        arch_cost = self.engine.get_cost_by_role(ExpertRoleTier.DISTINGUISHED_ARCHITECT)
        sec_cost = self.engine.get_cost_by_role(ExpertRoleTier.DOMAIN_SECURITY_EXPERT)

        self.assertEqual(qa_cost, 4500.0)
        self.assertEqual(arch_cost, 2000.0)
        self.assertEqual(sec_cost, 0.0)

    def test_get_total_human_cost_and_report(self) -> None:
        rep_empty = self.engine.get_human_expert_report()
        self.assertEqual(rep_empty["total_engagements"], 0)
        self.assertEqual(rep_empty["total_hours_logged"], 0.0)
        self.assertEqual(rep_empty["billable_ratio_pct"], 0.0)

        e = HumanExpertEngagement("e", "p", ExpertRoleTier.SENIOR_MIGRATION_ENGINEER, 200.0)
        self.engine.register_engagement(e)
        self.engine.log_hours("e", 30.0, is_billable=True)
        self.engine.log_hours("e", 10.0, is_billable=False)

        summary = self.engine.get_total_human_cost()
        self.assertEqual(summary.total_hours, 40.0)
        self.assertEqual(summary.total_billable_hours, 30.0)
        self.assertEqual(summary.total_cost_usd, 8000.0)
        self.assertEqual(summary.active_engagements_count, 1)

        rep = self.engine.get_human_expert_report()
        self.assertEqual(rep["total_hours_logged"], 40.0)
        self.assertEqual(rep["total_billable_hours"], 30.0)
        self.assertEqual(rep["billable_ratio_pct"], 75.0)
        self.assertEqual(rep["total_human_cost_usd"], 8000.0)


if __name__ == "__main__":
    unittest.main()
