import unittest
from datetime import datetime, timezone, timedelta

from elmos_mature_platform.types import (
    IncidentSeverity, IncidentStatus, EscalationTier, OnCallShift,
    OnCallEngineer, IncidentRecord, StatusPageUpdate, ServiceCatalogEntry,
    ChangeFreeze, CapacityPlan, RegionId
)
from elmos_mature_platform.incident_command_engine import IncidentCommandEngine

class TestIncidentCommandEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IncidentCommandEngine()

    def test_oncall_registration_and_lookup(self):
        eng = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng)
        found = self.engine.get_active_oncall(OnCallShift.APAC, EscalationTier.TIER_1)
        self.assertEqual(found.engineer_id, "eng1")

    def test_oncall_availability_when_at_max(self):
        eng = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC, current_incident_count=3)
        self.engine.register_oncall_engineer(eng)
        found = self.engine.get_active_oncall(OnCallShift.APAC, EscalationTier.TIER_1)
        self.assertIsNone(found)

    def test_declare_incident_auto_assign(self):
        eng = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng)
        self.engine.register_oncall_engineer(OnCallEngineer("eng2", "Bob", "b@test.com", EscalationTier.TIER_1, OnCallShift.EMEA))
        self.engine.register_oncall_engineer(OnCallEngineer("eng3", "Charlie", "c@test.com", EscalationTier.TIER_1, OnCallShift.AMERICAS))
        
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [RegionId.US_EAST_1])
        self.assertIsNotNone(inc.assigned_commander)
        self.assertEqual(inc.status, IncidentStatus.DECLARED)
        self.assertEqual(inc.severity, IncidentSeverity.SEV1)
        commander = next(e for e in self.engine.roster if e.engineer_id == inc.assigned_commander)
        self.assertEqual(commander.current_incident_count, 1)

    def test_declare_incident_no_oncall(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [RegionId.US_EAST_1])
        self.assertIsNone(inc.assigned_commander)

    def test_escalation_through_tiers(self):
        eng1 = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC)
        eng2 = OnCallEngineer("eng2", "Bob", "b@test.com", EscalationTier.TIER_2, OnCallShift.APAC)
        eng3 = OnCallEngineer("eng3", "Charlie", "c@test.com", EscalationTier.TIER_3, OnCallShift.APAC)
        eng4 = OnCallEngineer("eng4", "Dave", "d@test.com", EscalationTier.MANAGEMENT, OnCallShift.APAC)
        for e in [eng1, eng2, eng3, eng4]:
            self.engine.register_oncall_engineer(e)
            
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [RegionId.US_EAST_1])
        inc.assigned_commander = "eng1"
        eng1.current_incident_count = 1
        
        t2 = self.engine.escalate_incident("inc1", "need help")
        self.assertEqual(t2, EscalationTier.TIER_2)
        self.assertEqual(inc.assigned_commander, "eng2")
        self.assertEqual(eng1.current_incident_count, 0)
        self.assertEqual(eng2.current_incident_count, 1)

        t3 = self.engine.escalate_incident("inc1", "need more help")
        self.assertEqual(t3, EscalationTier.TIER_3)
        self.assertEqual(inc.assigned_commander, "eng3")

        tm = self.engine.escalate_incident("inc1", "manager help")
        self.assertEqual(tm, EscalationTier.MANAGEMENT)
        self.assertEqual(inc.assigned_commander, "eng4")

    def test_escalation_past_management_raises(self):
        eng4 = OnCallEngineer("eng4", "Dave", "d@test.com", EscalationTier.MANAGEMENT, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng4)
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        inc.assigned_commander = "eng4"
        with self.assertRaises(ValueError):
            self.engine.escalate_incident("inc1", "panic")

    def test_status_transitions_valid(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        self.engine.update_incident_status("inc1", IncidentStatus.TRIAGING, "started")
        self.assertEqual(inc.status, IncidentStatus.TRIAGING)
        self.engine.update_incident_status("inc1", IncidentStatus.MITIGATING, "mitigating")
        self.engine.update_incident_status("inc1", IncidentStatus.RESOLVED, "resolved")
        self.engine.update_incident_status("inc1", IncidentStatus.POST_MORTEM, "post mortem")
        self.engine.update_incident_status("inc1", IncidentStatus.CLOSED, "closed")
        self.assertEqual(inc.status, IncidentStatus.CLOSED)

    def test_status_transitions_invalid(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        with self.assertRaises(ValueError):
            self.engine.update_incident_status("inc1", IncidentStatus.RESOLVED, "skip to resolved")

    def test_resolve_incident(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        self.engine.resolve_incident("inc1", "Bad code")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)
        self.assertEqual(inc.root_cause, "Bad code")
        self.assertIsNotNone(inc.resolved_at)

    def test_status_page_update_generation(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        update = self.engine.generate_status_page_update("inc1", "API", "We are down")
        self.assertTrue(inc.customer_communication_sent)
        self.assertEqual(update.component, "API")

    def test_service_catalog_and_dependency_graph(self):
        self.engine.register_service(ServiceCatalogEntry("svc1", "A", "t1", "standard", dependencies=["svc2", "svc3"]))
        self.engine.register_service(ServiceCatalogEntry("svc2", "B", "t2", "standard", dependencies=["svc4"]))
        self.engine.register_service(ServiceCatalogEntry("svc3", "C", "t3", "standard", dependencies=[]))
        self.engine.register_service(ServiceCatalogEntry("svc4", "D", "t4", "standard", dependencies=[]))
        
        deps = self.engine.get_service_dependencies("svc1")
        self.assertCountEqual(deps, ["svc2", "svc3", "svc4"])

    def test_change_freeze_creation_and_enforcement(self):
        self.engine.create_change_freeze("f1", "holidays", 24, "global", "director")
        allowed, freeze_id = self.engine.is_change_allowed("svc1")
        self.assertFalse(allowed)
        self.assertEqual(freeze_id, "f1")

    def test_change_freeze_with_exceptions(self):
        freeze = self.engine.create_change_freeze("f1", "holidays", 24, "global", "director")
        freeze.exceptions.append("svc1")
        allowed, freeze_id = self.engine.is_change_allowed("svc1")
        self.assertTrue(allowed)
        allowed2, freeze_id2 = self.engine.is_change_allowed("svc2")
        self.assertFalse(allowed2)

    def test_autoscale_scale_up(self):
        plan = CapacityPlan("p1", "svc1", RegionId.US_EAST_1, 1, 10, 5, 70.0, 80.0)
        self.engine.create_capacity_plan(plan)
        action, new_count = self.engine.evaluate_autoscale("svc1", RegionId.US_EAST_1, 80.0, 50.0)
        self.assertEqual(action, "scale_up")
        self.assertEqual(new_count, 6)

    def test_autoscale_scale_down(self):
        plan = CapacityPlan("p1", "svc1", RegionId.US_EAST_1, 1, 10, 5, 70.0, 80.0)
        self.engine.create_capacity_plan(plan)
        action, new_count = self.engine.evaluate_autoscale("svc1", RegionId.US_EAST_1, 20.0, 50.0)
        self.assertEqual(action, "scale_down")
        self.assertEqual(new_count, 4)

    def test_autoscale_no_change(self):
        plan = CapacityPlan("p1", "svc1", RegionId.US_EAST_1, 1, 10, 5, 70.0, 80.0)
        self.engine.create_capacity_plan(plan)
        action, new_count = self.engine.evaluate_autoscale("svc1", RegionId.US_EAST_1, 50.0, 50.0)
        self.assertEqual(action, "no_change")
        self.assertEqual(new_count, 5)

    def test_autoscale_respects_max(self):
        plan = CapacityPlan("p1", "svc1", RegionId.US_EAST_1, 1, 10, 10, 70.0, 80.0)
        self.engine.create_capacity_plan(plan)
        action, new_count = self.engine.evaluate_autoscale("svc1", RegionId.US_EAST_1, 90.0, 50.0)
        self.assertEqual(action, "no_change")
        self.assertEqual(new_count, 10)

    def test_autoscale_respects_min(self):
        plan = CapacityPlan("p1", "svc1", RegionId.US_EAST_1, 1, 10, 1, 70.0, 80.0)
        self.engine.create_capacity_plan(plan)
        action, new_count = self.engine.evaluate_autoscale("svc1", RegionId.US_EAST_1, 10.0, 50.0)
        self.assertEqual(action, "no_change")
        self.assertEqual(new_count, 1)

    def test_incident_timeline_ordering(self):
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        self.engine.update_incident_status("inc1", IncidentStatus.TRIAGING, "triaging")
        self.engine.escalate_incident("inc1", "need help")
        timeline = self.engine.get_incident_timeline("inc1")
        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]["status"], IncidentStatus.DECLARED.value)
        self.assertEqual(timeline[1]["status"], IncidentStatus.TRIAGING.value)
        self.assertEqual(timeline[2]["type"], "escalation")

    def test_mttr_computation(self):
        inc1 = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        inc2 = self.engine.declare_incident("inc2", "Outage2", IncidentSeverity.SEV1, "user1", "ten1", [])
        
        now = datetime.now(timezone.utc)
        inc1.declared_at = (now - timedelta(minutes=60)).isoformat()
        self.engine.resolve_incident("inc1", "RC1")
        inc1.resolved_at = now.isoformat()
        
        inc2.declared_at = (now - timedelta(minutes=120)).isoformat()
        self.engine.resolve_incident("inc2", "RC2")
        inc2.resolved_at = now.isoformat()
        
        mttr = self.engine.compute_mttr()
        self.assertAlmostEqual(mttr[IncidentSeverity.SEV1.value], 90 * 60, delta=1.0)

    def test_multiple_concurrent_incidents_tracking(self):
        self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        self.engine.declare_incident("inc2", "Outage", IncidentSeverity.SEV2, "user1", "ten1", [])
        self.assertEqual(len(self.engine.incidents), 2)

    def test_active_incidents_filtering(self):
        inc1 = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        inc2 = self.engine.declare_incident("inc2", "Outage", IncidentSeverity.SEV2, "user1", "ten1", [])
        self.engine.resolve_incident("inc1", "RC1")
        self.engine.update_incident_status("inc1", IncidentStatus.POST_MORTEM, "pm")
        self.engine.update_incident_status("inc1", IncidentStatus.CLOSED, "closed")
        active = self.engine.get_active_incidents()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].incident_id, "inc2")

    def test_oncall_shift_mismatch(self):
        eng = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng)
        found = self.engine.get_active_oncall(OnCallShift.EMEA, EscalationTier.TIER_1)
        self.assertIsNone(found)

    def test_oncall_tier_mismatch(self):
        eng = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_2, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng)
        found = self.engine.get_active_oncall(OnCallShift.APAC, EscalationTier.TIER_1)
        self.assertIsNone(found)

    def test_escalation_no_available_engineer(self):
        eng1 = OnCallEngineer("eng1", "Alice", "a@test.com", EscalationTier.TIER_1, OnCallShift.APAC)
        self.engine.register_oncall_engineer(eng1)
        # Tier 2 is empty
        inc = self.engine.declare_incident("inc1", "Outage", IncidentSeverity.SEV1, "user1", "ten1", [])
        inc.assigned_commander = "eng1"
        eng1.current_incident_count = 1
        
        # Escalate to Tier 2
        tier = self.engine.escalate_incident("inc1", "need help")
        self.assertEqual(tier, EscalationTier.TIER_2)
        # Commander should be None since no TIER_2 exists
        self.assertIsNone(inc.assigned_commander)
        # Eng1 count should be decremented
        self.assertEqual(eng1.current_incident_count, 0)

    def test_service_dependency_not_in_catalog(self):
        self.engine.register_service(ServiceCatalogEntry("svc1", "A", "t1", "standard", dependencies=["missing_svc"]))
        deps = self.engine.get_service_dependencies("svc1")
        self.assertCountEqual(deps, ["missing_svc"])

if __name__ == '__main__':
    unittest.main()
