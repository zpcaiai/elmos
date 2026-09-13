import unittest
from elmos_mature_platform.global_sre_operations_factory_engine import (
    GlobalSreOperationsFactoryEngine,
)
from elmos_mature_platform.types import (
    EscalationTier,
    SreOncallShift,
    SrePlaybook,
    SreShiftRegion,
)


class TestGlobalSreOperationsFactoryComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = GlobalSreOperationsFactoryEngine()

    def test_schedule_and_activate_shifts(self):
        shift = SreOncallShift(
            shift_id="shift-apac-1",
            region=SreShiftRegion.APAC,
            start_time="00:00Z",
            end_time="08:00Z",
            primary_engineer="sre-alice@elmos.io",
            secondary_engineer="sre-bob@elmos.io",
        )
        s_id = self.engine.schedule_oncall_shift(shift)
        self.assertEqual(s_id, "shift-apac-1")

        active = self.engine.activate_shift("shift-apac-1")
        self.assertTrue(active.is_active)
        self.assertEqual(self.engine.get_active_shift(SreShiftRegion.APAC), active)

    def test_playbook_registration(self):
        pb = SrePlaybook(
            playbook_id="pb-oom-remediation",
            title="Pod Out-of-Memory Automated Remediation",
            service_tag="k8s-platform",
            steps=["Check OOM events", "Scale HPA target memory", "Recycle deployment"],
            automated_remediation_command="kubectl rollout restart deployment/worker",
        )
        pb_id = self.engine.register_playbook(pb)
        self.assertEqual(pb_id, "pb-oom-remediation")

    def test_incident_escalation_and_acknowledgement(self):
        shift = SreOncallShift(
            shift_id="shift-amer-1",
            region=SreShiftRegion.AMER,
            start_time="08:00Z",
            end_time="16:00Z",
            primary_engineer="sre-charlie@elmos.io",
            secondary_engineer="sre-dan@elmos.io",
            is_active=True,
        )
        self.engine.schedule_oncall_shift(shift)

        esc = self.engine.trigger_incident_escalation("INC-9001", "P1", SreShiftRegion.AMER)
        self.assertEqual(esc.severity, "P1")
        self.assertEqual(esc.response_sla_minutes, 15)
        self.assertEqual(esc.assigned_engineer, "sre-charlie@elmos.io")
        self.assertFalse(esc.acknowledged)

        unack = self.engine.get_unacknowledged_escalations()
        self.assertEqual(len(unack), 1)

        acked = self.engine.acknowledge_incident(esc.escalation_id, "sre-charlie@elmos.io")
        self.assertTrue(acked.acknowledged)

        # Escalate to Tier 2
        tiered = self.engine.escalate_to_next_tier(esc.escalation_id, EscalationTier.TIER_2_TECH_LEAD)
        self.assertEqual(tiered.current_tier, EscalationTier.TIER_2_TECH_LEAD)
        self.assertFalse(tiered.acknowledged)

        report = self.engine.get_global_sre_operations_report()
        self.assertEqual(report["total_escalations"], 1)
        self.assertEqual(report["p1_incident_count"], 1)


if __name__ == "__main__":
    unittest.main()
