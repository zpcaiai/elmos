"""Unit tests verifying the FDE Autonomous Delivery lifecycle and stage orchestration."""

from __future__ import annotations

import unittest

from elmos_fde_delivery.orchestrator import FDE_PHASES, FdeDeliveryOrchestrator


class TestFdeLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = FdeDeliveryOrchestrator()

    def test_phases_definition(self) -> None:
        self.assertEqual(len(FDE_PHASES), 6)

    def test_run_each_stage_independently(self) -> None:
        for pack_id, _ in FDE_PHASES:
            with self.subTest(pack=pack_id):
                result = self.orchestrator.run_stage(pack_id)
                self.assertEqual(result["status"], "PASS")
                self.assertGreater(result["skill_count"], 0)
                self.assertEqual(len(result["step_results"]), result["skill_count"])

    def test_run_full_lifecycle(self) -> None:
        result = self.orchestrator.run_full_lifecycle()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["phases_executed"], 6)
        self.assertEqual(result["total_phases"], 6)
        self.assertEqual(result["skills_executed_count"], 45)
        self.assertEqual(result["standalone_boundary"], "E3")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")
        self.assertFalse(result["production_ready"])

    def test_stage_failure_stops_lifecycle(self) -> None:
        # sow_approved=False will cause pilot-scope-sow-acceptance in Pack 01 to return FAIL
        result = self.orchestrator.run_full_lifecycle({"sow_approved": False})
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["phases_executed"], 1)
        self.assertLess(result["skills_executed_count"], 45)
