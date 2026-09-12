import unittest
from elmos_mature_platform.portable_control_plane_engine import PortableControlPlaneEngine
from elmos_mature_platform.types import (
    ControlPlaneComponent,
    PlaneHealthState,
    PortablePlaneType,
    DeploymentTopology,
    PlaneGovernanceRule
)

class TestPortableControlPlaneEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PortableControlPlaneEngine()

    def test_register_and_get_component(self):
        comp = ControlPlaneComponent(
            component_id="comp1",
            plane_type=PortablePlaneType.CONTROL,
            version="1.0",
            topology=DeploymentTopology.SINGLE_REGION
        )
        self.engine.register_component(comp)
        res = self.engine.get_component("comp1")
        self.assertEqual(res.component_id, "comp1")

    def test_get_nonexistent_component(self):
        with self.assertRaises(ValueError):
            self.engine.get_component("missing")

    def test_list_all_components(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.DATA, "1.0", DeploymentTopology.SINGLE_REGION))
        res = self.engine.list_components()
        self.assertEqual(len(res), 2)

    def test_list_filtered_components(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.DATA, "1.0", DeploymentTopology.SINGLE_REGION))
        res = self.engine.list_components(PortablePlaneType.CONTROL)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].component_id, "c1")

    def test_list_components_empty(self):
        self.assertEqual(len(self.engine.list_components()), 0)

    def test_update_health(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION))
        self.engine.update_health("c1", PlaneHealthState.RUNNING)
        self.assertEqual(self.engine.get_component("c1").health, PlaneHealthState.RUNNING)

    def test_update_health_missing(self):
        with self.assertRaises(ValueError):
            self.engine.update_health("missing", PlaneHealthState.RUNNING)

    def test_update_health_degraded(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION))
        self.engine.update_health("c1", PlaneHealthState.DEGRADED)
        self.assertEqual(self.engine.get_component("c1").health, PlaneHealthState.DEGRADED)

    def test_add_and_check_governance(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, requires_encryption=True))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, endpoint_url="http://fail"))
        res = self.engine.check_governance("c1")
        self.assertFalse(res["compliant"])
        self.assertIn("Endpoint URL must be https:// when encryption is required", res["reasons"])

    def test_governance_compliant(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, requires_encryption=True))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, endpoint_url="https://pass"))
        res = self.engine.check_governance("c1")
        self.assertTrue(res["compliant"])

    def test_governance_missing_rule(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION))
        res = self.engine.check_governance("c1")
        self.assertTrue(res["compliant"])

    def test_governance_missing_component(self):
        with self.assertRaises(ValueError):
            self.engine.check_governance("c1")

    def test_governance_topology_allowed(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, allowed_topologies=["single_region"]))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, endpoint_url="https://pass"))
        res = self.engine.check_governance("c1")
        self.assertTrue(res["compliant"])

    def test_governance_topology_denied(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, allowed_topologies=["multi_region"]))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, endpoint_url="https://pass"))
        res = self.engine.check_governance("c1")
        self.assertFalse(res["compliant"])

    def test_get_topology_resource_summary(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, resource_cpu_millicores=100, resource_memory_mb=200))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, resource_cpu_millicores=150, resource_memory_mb=300))
        res = self.engine.get_topology_resource_summary(DeploymentTopology.SINGLE_REGION)
        self.assertEqual(res["total_cpu_millicores"], 250)
        self.assertEqual(res["total_memory_mb"], 500)
        self.assertEqual(res["component_count"], 2)

    def test_get_topology_resource_summary_empty(self):
        res = self.engine.get_topology_resource_summary(DeploymentTopology.SINGLE_REGION)
        self.assertEqual(res["total_cpu_millicores"], 0)
        self.assertEqual(res["total_memory_mb"], 0)

    def test_validate_topology_valid(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, min_instances=1, max_instances=3))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.RUNNING))
        res = self.engine.validate_topology(DeploymentTopology.SINGLE_REGION)
        self.assertTrue(res.valid)

    def test_validate_topology_unhealthy(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, min_instances=1, max_instances=3))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.STOPPED))
        res = self.engine.validate_topology(DeploymentTopology.SINGLE_REGION)
        self.assertFalse(res.valid)

    def test_validate_topology_airgapped_regions(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.AIR_GAPPED, region="us-east", health=PlaneHealthState.RUNNING))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.DATA, "1.0", DeploymentTopology.AIR_GAPPED, region="us-west", health=PlaneHealthState.RUNNING))
        res = self.engine.validate_topology(DeploymentTopology.AIR_GAPPED)
        self.assertFalse(res.valid)
        self.assertIn("Air-gapped topology requires all components in same region", res.warnings)

    def test_validate_topology_min_instances(self):
        self.engine.add_governance_rule(PlaneGovernanceRule("r1", PortablePlaneType.CONTROL, min_instances=2))
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.RUNNING))
        res = self.engine.validate_topology(DeploymentTopology.SINGLE_REGION)
        self.assertFalse(res.valid)

    def test_detect_no_dependency_issues(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.RUNNING))
        res = self.engine.detect_dependency_issues()
        self.assertEqual(len(res), 0)

    def test_detect_missing_dependency(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, dependencies=["missing"]))
        res = self.engine.detect_dependency_issues()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["type"], "missing_dependency")

    def test_detect_unhealthy_dependency(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, dependencies=["c2"]))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.STOPPED))
        res = self.engine.detect_dependency_issues()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["type"], "unhealthy_dependency")

    def test_detect_circular_dependency(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, dependencies=["c2"]))
        self.engine.register_component(ControlPlaneComponent("c2", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, dependencies=["c1"]))
        res = self.engine.detect_dependency_issues()
        cycles = [r for r in res if r["type"] == "circular_dependency"]
        self.assertTrue(len(cycles) > 0)

    def test_promote_topology_success(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.RUNNING))
        res = self.engine.promote_topology(DeploymentTopology.SINGLE_REGION, DeploymentTopology.MULTI_REGION)
        self.assertTrue(res["success"])

    def test_promote_topology_fail_unhealthy(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.STOPPED))
        res = self.engine.promote_topology(DeploymentTopology.SINGLE_REGION, DeploymentTopology.MULTI_REGION)
        self.assertFalse(res["success"])

    def test_promote_topology_fail_dependencies(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, dependencies=["missing"], health=PlaneHealthState.RUNNING))
        res = self.engine.promote_topology(DeploymentTopology.SINGLE_REGION, DeploymentTopology.MULTI_REGION)
        self.assertFalse(res["success"])

    def test_health_report_healthy(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.RUNNING))
        res = self.engine.get_plane_health_report()
        self.assertEqual(res[PortablePlaneType.CONTROL.value]["overall_state"], "healthy")

    def test_health_report_degraded(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.STOPPED))
        res = self.engine.get_plane_health_report()
        self.assertEqual(res[PortablePlaneType.CONTROL.value]["overall_state"], "degraded")

    def test_health_report_unreachable(self):
        self.engine.register_component(ControlPlaneComponent("c1", PortablePlaneType.CONTROL, "1.0", DeploymentTopology.SINGLE_REGION, health=PlaneHealthState.UNREACHABLE))
        res = self.engine.get_plane_health_report()
        self.assertEqual(res[PortablePlaneType.CONTROL.value]["overall_state"], "degraded")

if __name__ == '__main__':
    unittest.main()
