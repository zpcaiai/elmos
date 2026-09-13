"""Comprehensive test suite for GlobalOperationsGateEngine (B39 - Skill 1360)."""

import unittest

from elmos_mature_platform.global_operations_gate_engine import (
    GlobalOperationsGateEngine,
)
from elmos_mature_platform.types import (
    GateCheckCategory,
    GateVerdict,
    OperationsGateCheck,
)


class TestGlobalOperationsGateComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = GlobalOperationsGateEngine()

    def test_create_gate_request_auto_adds_freeze_check(self):
        dec = self.engine.create_gate_request("rel-1.0.0", "production")
        self.assertIsNotNone(dec)
        self.assertEqual(len(dec.checks), 1)
        self.assertEqual(dec.checks[0].category, GateCheckCategory.CHANGE_FREEZE)
        self.assertTrue(dec.checks[0].passed)

    def test_change_freeze_blocks_request(self):
        self.engine.set_change_freeze("production", active=True, reason="Black Friday Freeze")
        self.assertTrue(self.engine.is_change_freeze_active("production"))

        dec = self.engine.create_gate_request("rel-1.0.1", "production")
        self.assertFalse(dec.checks[0].passed)

        evaluated = self.engine.evaluate_gate(dec.decision_id)
        self.assertEqual(evaluated.overall_verdict, GateVerdict.REJECTED)

    def test_clear_change_freeze(self):
        self.engine.set_change_freeze("staging", active=True, reason="Maintenance")
        self.assertTrue(self.engine.is_change_freeze_active("staging"))
        self.engine.set_change_freeze("staging", active=False)
        self.assertFalse(self.engine.is_change_freeze_active("staging"))

    def test_slo_check_healthy_and_unhealthy(self):
        dec = self.engine.create_gate_request("rel-2.0.0", "staging")

        # Healthy check
        chk1 = self.engine.record_slo_check(dec.decision_id, "auth-service", 45.0, min_required_pct=20.0)
        self.assertTrue(chk1.passed)

        # Unhealthy check
        chk2 = self.engine.record_slo_check(dec.decision_id, "billing-service", 12.0, min_required_pct=20.0)
        self.assertFalse(chk2.passed)

        evaluated = self.engine.evaluate_gate(dec.decision_id)
        self.assertEqual(evaluated.overall_verdict, GateVerdict.REJECTED)

    def test_incident_check_zero_tolerance_p1(self):
        dec = self.engine.create_gate_request("rel-2.0.1", "production")
        chk = self.engine.record_incident_check(dec.decision_id, active_p1_count=1, active_p2_count=3)
        self.assertFalse(chk.passed)

        evaluated = self.engine.evaluate_gate(dec.decision_id)
        self.assertEqual(evaluated.overall_verdict, GateVerdict.REJECTED)

    def test_incident_check_passed_when_no_p1(self):
        dec = self.engine.create_gate_request("rel-2.0.2", "production")
        chk = self.engine.record_incident_check(dec.decision_id, active_p1_count=0, active_p2_count=2)
        self.assertTrue(chk.passed)

    def test_oncall_check_assigned(self):
        dec = self.engine.create_gate_request("rel-2.0.3", "production")
        chk = self.engine.record_oncall_check(dec.decision_id, "stephen@elmos.io", "backup@elmos.io")
        self.assertTrue(chk.passed)

    def test_oncall_check_unassigned_fails(self):
        dec = self.engine.create_gate_request("rel-2.0.4", "production")
        chk = self.engine.record_oncall_check(dec.decision_id, "")
        self.assertFalse(chk.passed)

    def test_all_checks_passed_yields_approved(self):
        dec = self.engine.create_gate_request("rel-clean", "production")
        self.engine.record_slo_check(dec.decision_id, "all-services", 85.0)
        self.engine.record_incident_check(dec.decision_id, active_p1_count=0, active_p2_count=0)
        self.engine.record_oncall_check(dec.decision_id, "lead-sre")

        evaluated = self.engine.evaluate_gate(dec.decision_id, approver="release-manager")
        self.assertEqual(evaluated.overall_verdict, GateVerdict.APPROVED)
        self.assertEqual(evaluated.approved_by, "release-manager")

    def test_non_blocking_failure_yields_conditional_approval(self):
        dec = self.engine.create_gate_request("rel-cond", "staging")
        non_blocking_check = OperationsGateCheck(
            check_id="chk-nb-1",
            category=GateCheckCategory.CAPACITY_MARGIN,
            name="Storage Capacity Warning",
            passed=False,
            current_value=12.0,
            threshold_value=15.0,
            details="Storage margin low but within staging threshold",
            blocking=False,
        )
        self.engine.add_check(dec.decision_id, non_blocking_check)

        evaluated = self.engine.evaluate_gate(dec.decision_id, approver="stage-admin")
        self.assertEqual(evaluated.overall_verdict, GateVerdict.CONDITIONAL_APPROVAL)

    def test_emergency_override_approval(self):
        self.engine.set_change_freeze("production", active=True, reason="Strict Freeze")
        dec = self.engine.create_gate_request("hotfix-critical", "production")
        self.assertFalse(dec.checks[0].passed)

        # Normal eval would fail
        normal_eval = self.engine.evaluate_gate(dec.decision_id)
        self.assertEqual(normal_eval.overall_verdict, GateVerdict.REJECTED)

        # Emergency override by VP Engineering
        override_eval = self.engine.evaluate_gate(
            dec.decision_id,
            emergency_override=True,
            approver="vp-engineering@elmos.io",
            override_reason="P0 security hotfix patch addressing active exploit",
        )
        self.assertEqual(override_eval.overall_verdict, GateVerdict.OVERRIDE_APPROVED)
        self.assertTrue(override_eval.emergency_override)
        self.assertEqual(override_eval.approved_by, "vp-engineering@elmos.io")

    def test_emergency_override_missing_justification_raises(self):
        dec = self.engine.create_gate_request("hotfix-bad", "production")
        with self.assertRaises(ValueError):
            self.engine.evaluate_gate(dec.decision_id, emergency_override=True, approver="", override_reason="")

    def test_gate_summary_metrics(self):
        dec1 = self.engine.create_gate_request("r1", "staging")
        self.engine.evaluate_gate(dec1.decision_id)

        dec2 = self.engine.create_gate_request("r2", "production")
        self.engine.evaluate_gate(dec2.decision_id, emergency_override=True, approver="admin", override_reason="reason")

        summary = self.engine.get_gate_summary()
        self.assertEqual(summary["total_decisions"], 2)
        self.assertIn("approved", summary["verdicts"])
        self.assertGreaterEqual(summary["approval_rate_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
