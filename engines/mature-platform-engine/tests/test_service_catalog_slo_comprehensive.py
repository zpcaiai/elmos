import unittest
from datetime import datetime
from elmos_mature_platform.types import (
    ServiceEntry, SliDefinition, SloTarget, SloMeasurement, ServiceTier, SliType
)
from elmos_mature_platform.service_catalog_slo_engine import ServiceCatalogSloEngine

class TestServiceCatalogSloEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ServiceCatalogSloEngine()
        
    def test_register_service(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.assertEqual(self.engine.register_service(svc), "s1")
        self.assertEqual(self.engine.get_service("s1").name, "Service 1")
        
    def test_register_duplicate_service(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        with self.assertRaises(ValueError):
            self.engine.register_service(svc)
            
    def test_register_service_with_invalid_dependency(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a", dependencies=["nonexistent"])
        with self.assertRaises(ValueError):
            self.engine.register_service(svc)

    def test_register_service_with_valid_dependency(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc1)
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.assertEqual(self.engine.register_service(svc2), "s2")

    def test_update_service(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        self.engine.update_service("s1", name="Updated Service 1", owner_team="team-b")
        updated = self.engine.get_service("s1")
        self.assertEqual(updated.name, "Updated Service 1")
        self.assertEqual(updated.owner_team, "team-b")

    def test_update_nonexistent_service(self):
        with self.assertRaises(ValueError):
            self.engine.update_service("s1", name="Updated Service 1")

    def test_update_service_invalid_dependency(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        with self.assertRaises(ValueError):
            self.engine.update_service("s1", dependencies=["nonexistent"])

    def test_decommission_service(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        self.assertTrue(self.engine.decommission_service("s1"))
        with self.assertRaises(ValueError):
            self.engine.get_service("s1")

    def test_decommission_nonexistent_service(self):
        with self.assertRaises(ValueError):
            self.engine.decommission_service("s1")

    def test_decommission_service_with_dependents(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.engine.register_service(svc1)
        self.engine.register_service(svc2)
        with self.assertRaises(ValueError):
            self.engine.decommission_service("s1")
            
    def test_decommission_cascades_to_slis_slos(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.9)
        self.engine.set_slo_target(slo)
        
        self.engine.decommission_service("s1")
        self.assertNotIn("sli1", self.engine._slis)
        self.assertNotIn("slo1", self.engine._slos)

    def test_define_sli(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.assertEqual(self.engine.define_sli(sli), "sli1")

    def test_define_sli_nonexistent_service(self):
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        with self.assertRaises(ValueError):
            self.engine.define_sli(sli)

    def test_define_duplicate_sli(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        with self.assertRaises(ValueError):
            self.engine.define_sli(sli)

    def test_set_slo_target(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.9)
        self.assertEqual(self.engine.set_slo_target(slo), "slo1")

    def test_set_slo_target_nonexistent_service(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="nonexistent", target_percentage=99.9)
        with self.assertRaises(ValueError):
            self.engine.set_slo_target(slo)

    def test_set_slo_target_nonexistent_sli(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        slo = SloTarget(slo_id="slo1", sli_id="nonexistent", service_id="s1", target_percentage=99.9)
        with self.assertRaises(ValueError):
            self.engine.set_slo_target(slo)

    def test_set_duplicate_slo_target(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.9)
        self.engine.set_slo_target(slo)
        with self.assertRaises(ValueError):
            self.engine.set_slo_target(slo)

    def test_record_measurement(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        # 99.5%
        meas = SloMeasurement(slo_id="slo1", good_events=995, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        self.assertEqual(meas.measured_percentage, 99.5)
        # budget_remaining = (99.5 - 99.0) / (100 - 99.0) * 100 = 0.5 / 1.0 * 100 = 50.0
        self.assertAlmostEqual(meas.budget_remaining_pct, 50.0)

    def test_record_measurement_zero_events(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        meas = SloMeasurement(slo_id="slo1", good_events=0, total_events=0, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        self.assertEqual(meas.measured_percentage, 100.0)
        self.assertEqual(meas.budget_remaining_pct, 100.0)

    def test_record_measurement_100_percent(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        meas = SloMeasurement(slo_id="slo1", good_events=1000, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        self.assertEqual(meas.measured_percentage, 100.0)
        self.assertEqual(meas.budget_remaining_pct, 100.0)

    def test_record_measurement_below_target(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        # 98.0%
        meas = SloMeasurement(slo_id="slo1", good_events=980, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        self.assertEqual(meas.measured_percentage, 98.0)
        self.assertEqual(meas.budget_remaining_pct, 0.0)

    def test_record_measurement_nonexistent_slo(self):
        meas = SloMeasurement(slo_id="nonexistent", good_events=995, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        with self.assertRaises(ValueError):
            self.engine.record_measurement(meas)

    def test_get_service_slos(self):
        svc = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        meas1 = SloMeasurement(slo_id="slo1", good_events=995, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        meas2 = SloMeasurement(slo_id="slo1", good_events=990, total_events=1000, measured_at="2024-01-02T00:00:00Z")
        self.engine.record_measurement(meas1)
        self.engine.record_measurement(meas2)
        
        slos = self.engine.get_service_slos("s1")
        self.assertEqual(len(slos), 1)
        self.assertEqual(slos[0]["slo"].slo_id, "slo1")
        self.assertEqual(slos[0]["sli"].sli_id, "sli1")
        self.assertEqual(slos[0]["latest_measurement"].measured_at, "2024-01-02T00:00:00Z")

    def test_get_service_slos_nonexistent_service(self):
        with self.assertRaises(ValueError):
            self.engine.get_service_slos("s1")

    def test_get_dependency_graph(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.engine.register_service(svc1)
        self.engine.register_service(svc2)
        
        graph = self.engine.get_dependency_graph()
        self.assertEqual(graph["s1"], [])
        self.assertEqual(graph["s2"], ["s1"])

    def test_detect_circular_dependencies_none(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.engine.register_service(svc1)
        self.engine.register_service(svc2)
        
        cycles = self.engine.detect_circular_dependencies()
        self.assertEqual(len(cycles), 0)

    def test_detect_circular_dependencies(self):
        # We need to bypass the register_service dependency check to create a cycle
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc1)
        
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.engine.register_service(svc2)
        
        # Create cycle
        self.engine.update_service("s1", dependencies=["s2"])
        
        cycles = self.engine.detect_circular_dependencies()
        self.assertEqual(len(cycles), 1)
        # It should contain s1, s2, s1
        self.assertTrue(cycles[0] == ["s1", "s2", "s1"] or cycles[0] == ["s2", "s1", "s2"])
        
    def test_get_tier_report(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc1)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        meas = SloMeasurement(slo_id="slo1", good_events=980, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        
        report = self.engine.get_tier_report()
        self.assertIn(ServiceTier.TIER_1.value, report)
        self.assertFalse(report[ServiceTier.TIER_1.value][0]["is_healthy"])

    def test_get_services_below_target(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        self.engine.register_service(svc1)
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        meas = SloMeasurement(slo_id="slo1", good_events=980, total_events=1000, measured_at="2024-01-01T00:00:00Z")
        self.engine.record_measurement(meas)
        
        below = self.engine.get_services_below_target()
        self.assertEqual(len(below), 1)
        self.assertEqual(below[0]["service_id"], "s1")

    def test_get_catalog_report(self):
        svc1 = ServiceEntry(service_id="s1", name="Service 1", tier=ServiceTier.TIER_1, owner_team="team-a")
        svc2 = ServiceEntry(service_id="s2", name="Service 2", tier=ServiceTier.TIER_2, owner_team="team-b", dependencies=["s1"])
        self.engine.register_service(svc1)
        self.engine.register_service(svc2)
        
        sli = SliDefinition(sli_id="sli1", service_id="s1", sli_type=SliType.AVAILABILITY)
        self.engine.define_sli(sli)
        slo = SloTarget(slo_id="slo1", sli_id="sli1", service_id="s1", target_percentage=99.0)
        self.engine.set_slo_target(slo)
        
        report = self.engine.get_catalog_report()
        self.assertEqual(report["total_services"], 2)
        self.assertEqual(report["total_slis"], 1)
        self.assertEqual(report["total_slos"], 1)
        self.assertEqual(report["services"]["s1"]["dependent_count"], 1)
        self.assertEqual(report["services"]["s1"]["dependency_count"], 0)
        self.assertEqual(report["services"]["s2"]["dependent_count"], 0)
        self.assertEqual(report["services"]["s2"]["dependency_count"], 1)

if __name__ == '__main__':
    unittest.main()
