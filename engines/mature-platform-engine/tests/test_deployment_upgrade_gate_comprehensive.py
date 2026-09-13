import unittest
from elmos_mature_platform.deployment_upgrade_gate_engine import DeploymentUpgradeGateEngine
from elmos_mature_platform.types import (
    DeploymentUpgradeGateCheck,
    UpgradeGateCheckType,
    UpgradeGateVerdict,
)


class TestDeploymentUpgradeGateComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = DeploymentUpgradeGateEngine()

    def test_initiate_assessment_validation(self):
        gate_id = self.engine.initiate_upgrade_assessment("dep-prod-1", "v1.2.0", "v1.3.0")
        self.assertTrue(bool(gate_id))
        self.assertTrue(gate_id.startswith("gate-"))

        with self.assertRaises(ValueError):
            self.engine.initiate_upgrade_assessment("dep-prod-1", "v1.2.0", "v1.2.0")

    def test_add_check_and_approve_gate(self):
        gate_id = self.engine.initiate_upgrade_assessment("dep-prod-2", "v2.0.0", "v2.1.0")
        c1 = DeploymentUpgradeGateCheck(
            check_id="chk-schema",
            check_type=UpgradeGateCheckType.SCHEMA_COMPATIBILITY,
            description="No Destructive Column Drops",
            is_blocking=True,
            passed=True,
        )
        c2 = DeploymentUpgradeGateCheck(
            check_id="chk-drain",
            check_type=UpgradeGateCheckType.TRAFFIC_DRAIN_SAFETY,
            description="Zero Active Connection Drops",
            is_blocking=True,
            passed=True,
        )
        self.engine.add_gate_check(gate_id, c1)
        self.engine.add_gate_check(gate_id, c2)

        ass = self.engine.evaluate_gate(gate_id, operator="release-lead")
        self.assertEqual(ass.verdict, UpgradeGateVerdict.APPROVED)

    def test_blocking_check_failure_blocks_gate(self):
        gate_id = self.engine.initiate_upgrade_assessment("dep-prod-3", "v1.0.0", "v2.0.0")
        c1 = DeploymentUpgradeGateCheck(
            check_id="chk-rollback",
            check_type=UpgradeGateCheckType.ROLLBACK_PLAN_READY,
            description="Rollback Script Dry-Run",
            is_blocking=True,
            passed=False,
        )
        self.engine.add_gate_check(gate_id, c1)

        ass = self.engine.evaluate_gate(gate_id)
        self.assertEqual(ass.verdict, UpgradeGateVerdict.BLOCKED)
        failed = self.engine.get_failed_blocking_checks(gate_id)
        self.assertEqual(len(failed), 1)

    def test_override_gate_and_report(self):
        gate_id = self.engine.initiate_upgrade_assessment("dep-prod-4", "v3.0.0", "v3.1.0")
        c1 = DeploymentUpgradeGateCheck(
            check_id="chk-err",
            check_type=UpgradeGateCheckType.CANARY_ERROR_BUDGET,
            description="Error Budget Remaining",
            is_blocking=True,
            passed=False,
        )
        self.engine.add_gate_check(gate_id, c1)
        self.engine.evaluate_gate(gate_id)

        overridden = self.engine.override_gate(
            gate_id, operator="vp-engineering", override_reason="Critical Zero-Day Security Patch CVE-2026-1188"
        )
        self.assertEqual(overridden.verdict, UpgradeGateVerdict.CONDITIONAL_OVERRIDE)

        rep = self.engine.get_upgrade_gate_report()
        self.assertEqual(rep["total_assessments"], 1)
        self.assertEqual(rep["overridden_count"], 1)


if __name__ == "__main__":
    unittest.main()
