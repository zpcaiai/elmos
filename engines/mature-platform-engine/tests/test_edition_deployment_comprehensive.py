import unittest
from datetime import datetime
import uuid

from elmos_mature_platform.types import (
    EditionDeployment,
    EditionType,
    UpgradePhase,
    VersionCompatibility,
    PlaneTopology,
    PlaneType,
    UpgradeStrategy,
    RegionId,
)
from elmos_mature_platform.edition_deployment_engine import EditionDeploymentEngine

class TestEditionDeploymentComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = EditionDeploymentEngine()

    def test_register_each_edition_type(self):
        for ed_type in EditionType:
            d = EditionDeployment(
                deployment_id=f"dep-{uuid.uuid4()}",
                edition_type=ed_type,
                tenant_id="t1",
                region=RegionId.US_EAST_1,
                version="1.0.0",
                max_tenants=5 if ed_type == EditionType.MULTITENANT_SAAS else 1,
                network_isolated=True if ed_type == EditionType.AIR_GAPPED else False
            )
            self.engine.register_edition(d)
            self.assertEqual(self.engine.get_deployment(d.deployment_id).edition_type, ed_type)

    def test_air_gapped_requires_network_isolated(self):
        d = EditionDeployment(
            deployment_id="dep-airgap",
            edition_type=EditionType.AIR_GAPPED,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            network_isolated=False
        )
        with self.assertRaisesRegex(ValueError, "network isolated"):
            self.engine.register_edition(d)

    def test_multitenant_requires_max_tenants_gt_1(self):
        d = EditionDeployment(
            deployment_id="dep-multi",
            edition_type=EditionType.MULTITENANT_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            max_tenants=1
        )
        with self.assertRaisesRegex(ValueError, "max_tenants > 1"):
            self.engine.register_edition(d)

    def test_version_compatibility_check_compatible(self):
        compat = VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True)
        self.engine.register_version_compatibility(compat)
        c = self.engine.check_upgrade_path("1.0.0", "1.1.0")
        self.assertTrue(c.compatible)

    def test_version_compatibility_check_incompatible(self):
        compat = VersionCompatibility(source_version="1.0.0", target_version="2.0.0", compatible=False, breaking_changes=["API v1 removed"])
        self.engine.register_version_compatibility(compat)
        c = self.engine.check_upgrade_path("1.0.0", "2.0.0")
        self.assertFalse(c.compatible)
        self.assertIn("API v1 removed", c.breaking_changes)

    def test_initiate_upgrade_success(self):
        d = EditionDeployment(
            deployment_id="dep-upg",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0"
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True))
        
        upg = self.engine.initiate_upgrade("dep-upg", "1.1.0")
        self.assertEqual(upg.phase, UpgradePhase.PRE_CHECK)
        self.assertEqual(upg.from_version, "1.0.0")
        self.assertEqual(upg.to_version, "1.1.0")

    def test_initiate_upgrade_incompatible_raises(self):
        d = EditionDeployment(
            deployment_id="dep-upg",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0"
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="2.0.0", compatible=False))
        
        with self.assertRaisesRegex(ValueError, "Incompatible"):
            self.engine.initiate_upgrade("dep-upg", "2.0.0")

    def test_advance_upgrade_through_all_phases(self):
        d = EditionDeployment(
            deployment_id="dep-upg2",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0"
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True))
        
        upg = self.engine.initiate_upgrade("dep-upg2", "1.1.0")
        
        phases = [
            UpgradePhase.BACKUP,
            UpgradePhase.EXPAND,
            UpgradePhase.MIGRATE,
            UpgradePhase.VERIFY,
            UpgradePhase.CONTRACT,
            UpgradePhase.COMPLETE,
        ]
        
        for phase in phases:
            upg = self.engine.advance_upgrade_phase(upg.upgrade_id)
            self.assertEqual(upg.phase, phase)
            
        # check completed
        self.assertIsNotNone(upg.completed_at)
        dep = self.engine.get_deployment("dep-upg2")
        self.assertEqual(dep.version, "1.1.0")
        self.assertEqual(dep.previous_version, "1.0.0")

    def test_rollback_upgrade_success(self):
        d = EditionDeployment(
            deployment_id="dep-rb",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0"
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True))
        
        upg = self.engine.initiate_upgrade("dep-rb", "1.1.0")
        self.engine.advance_upgrade_phase(upg.upgrade_id) # to backup
        
        rb_upg = self.engine.rollback_upgrade(upg.upgrade_id)
        self.assertEqual(rb_upg.phase, UpgradePhase.ROLLBACK)
        self.assertIn("Rollback initiated", rb_upg.migration_log[-1])

    def test_rollback_after_complete_fails(self):
        d = EditionDeployment(
            deployment_id="dep-rb2",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0"
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True))
        
        upg = self.engine.initiate_upgrade("dep-rb2", "1.1.0")
        while upg.phase != UpgradePhase.COMPLETE:
            upg = self.engine.advance_upgrade_phase(upg.upgrade_id)
            
        with self.assertRaisesRegex(ValueError, "Cannot rollback a completed upgrade"):
            self.engine.rollback_upgrade(upg.upgrade_id)

    def test_zero_downtime_upgrade_end_to_end(self):
        d = EditionDeployment(
            deployment_id="dep-zdt",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            upgrade_strategy=UpgradeStrategy.ROLLING_UPDATE
        )
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0.0", target_version="1.1.0", compatible=True))
        
        upg = self.engine.execute_zero_downtime_upgrade("dep-zdt", "1.1.0")
        self.assertEqual(upg.phase, UpgradePhase.COMPLETE)
        self.assertEqual(self.engine.get_deployment("dep-zdt").version, "1.1.0")

    def test_plane_topology_registration_and_validation(self):
        d = EditionDeployment(
            deployment_id="dep-plane",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            planes=[PlaneType.CONTROL_PLANE, PlaneType.DATA_PLANE]
        )
        self.engine.register_edition(d)
        
        topo = PlaneTopology(
            topology_id="topo-1",
            deployment_id="dep-plane",
            planes={
                "control_plane": {"region": "us-east-1", "replicas": 3},
                "data_plane": {"region": "us-east-1", "replicas": 5}
            },
            cross_plane_connectivity=[("control_plane", "data_plane")]
        )
        self.engine.register_plane_topology(topo)
        
        self.assertIn("dep-plane", self.engine._topologies)

    def test_plane_connectivity_validation_all_connected(self):
        d = EditionDeployment(
            deployment_id="dep-conn",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            planes=[PlaneType.CONTROL_PLANE, PlaneType.DATA_PLANE]
        )
        self.engine.register_edition(d)
        
        topo = PlaneTopology(
            topology_id="topo-2",
            deployment_id="dep-conn",
            cross_plane_connectivity=[("control_plane", "data_plane"), ("data_plane", "control_plane")]
        )
        self.engine.register_plane_topology(topo)
        
        conn = self.engine.validate_plane_connectivity("dep-conn")
        self.assertTrue(conn["control_plane->data_plane"])
        self.assertTrue(conn["data_plane->control_plane"])

    def test_plane_connectivity_validation_missing_connection(self):
        d = EditionDeployment(
            deployment_id="dep-conn2",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            planes=[PlaneType.CONTROL_PLANE, PlaneType.DATA_PLANE]
        )
        self.engine.register_edition(d)
        
        topo = PlaneTopology(
            topology_id="topo-3",
            deployment_id="dep-conn2",
            cross_plane_connectivity=[("control_plane", "data_plane")]
        )
        self.engine.register_plane_topology(topo)
        
        conn = self.engine.validate_plane_connectivity("dep-conn2")
        self.assertTrue(conn["control_plane->data_plane"])
        self.assertFalse(conn["data_plane->control_plane"])

    def test_edition_responsibility_matrix_multitenant(self):
        matrix = self.engine.get_edition_responsibility_matrix(EditionType.MULTITENANT_SAAS)
        self.assertEqual(matrix["control_plane"], "platform")
        self.assertEqual(matrix["data_plane"], "platform")
        self.assertEqual(matrix["networking"], "platform")

    def test_edition_responsibility_matrix_self_hosted(self):
        matrix = self.engine.get_edition_responsibility_matrix(EditionType.SELF_HOSTED)
        self.assertEqual(matrix["control_plane"], "customer")
        self.assertEqual(matrix["data_plane"], "customer")
        self.assertEqual(matrix["updates"], "customer")

    def test_offline_update_bundle_for_air_gapped(self):
        d = EditionDeployment(
            deployment_id="dep-air",
            edition_type=EditionType.AIR_GAPPED,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            network_isolated=True
        )
        self.engine.register_edition(d)
        
        bundle = self.engine.create_offline_update_bundle("dep-air", "1.1.0")
        self.assertEqual(bundle["target_version"], "1.1.0")
        self.assertIn("signature", bundle)

    def test_data_residency_validation_compliant(self):
        d = EditionDeployment(
            deployment_id="dep-res",
            edition_type=EditionType.PRIVATE_SOVEREIGN,
            tenant_id="t1",
            region=RegionId.EU_WEST_1,
            version="1.0.0",
            data_residency_region="eu-west-1"
        )
        self.engine.register_edition(d)
        
        topo = PlaneTopology(
            topology_id="topo-res",
            deployment_id="dep-res",
            planes={
                "control_plane": {"region": "eu-west-1"},
                "data_plane": {"region": "eu-west-1"}
            }
        )
        self.engine.register_plane_topology(topo)
        
        compliant, violations = self.engine.validate_data_residency("dep-res")
        self.assertTrue(compliant)
        self.assertEqual(len(violations), 0)

    def test_data_residency_validation_violation(self):
        d = EditionDeployment(
            deployment_id="dep-res2",
            edition_type=EditionType.PRIVATE_SOVEREIGN,
            tenant_id="t1",
            region=RegionId.US_EAST_1, # Violation: Should be eu-west-1
            version="1.0.0",
            data_residency_region="eu-west-1"
        )
        self.engine.register_edition(d)
        
        topo = PlaneTopology(
            topology_id="topo-res2",
            deployment_id="dep-res2",
            planes={
                "control_plane": {"region": "eu-west-1"},
                "data_plane": {"region": "us-east-1"} # Violation
            }
        )
        self.engine.register_plane_topology(topo)
        
        compliant, violations = self.engine.validate_data_residency("dep-res2")
        self.assertFalse(compliant)
        self.assertEqual(len(violations), 2)

    def test_active_deployments_filtering(self):
        d1 = EditionDeployment(deployment_id="dep-1", edition_type=EditionType.MULTITENANT_SAAS, tenant_id="t1", region=RegionId.US_EAST_1, version="1.0", max_tenants=10)
        d2 = EditionDeployment(deployment_id="dep-2", edition_type=EditionType.DEDICATED_SAAS, tenant_id="t2", region=RegionId.US_EAST_1, version="1.0")
        d3 = EditionDeployment(deployment_id="dep-3", edition_type=EditionType.DEDICATED_SAAS, tenant_id="t3", region=RegionId.US_EAST_1, version="1.0", is_active=False)
        
        self.engine.register_edition(d1)
        self.engine.register_edition(d2)
        self.engine.register_edition(d3)
        
        all_active = self.engine.get_active_deployments()
        self.assertEqual(len(all_active), 2)
        
        ded_active = self.engine.get_active_deployments(EditionType.DEDICATED_SAAS)
        self.assertEqual(len(ded_active), 1)
        self.assertEqual(ded_active[0].deployment_id, "dep-2")

    def test_multiple_deployments_for_same_tenant(self):
        d1 = EditionDeployment(deployment_id="dep-t1-1", edition_type=EditionType.DEDICATED_SAAS, tenant_id="t1", region=RegionId.US_EAST_1, version="1.0")
        d2 = EditionDeployment(deployment_id="dep-t1-2", edition_type=EditionType.CUSTOMER_VPC, tenant_id="t1", region=RegionId.US_EAST_1, version="1.0")
        
        self.engine.register_edition(d1)
        self.engine.register_edition(d2)
        
        deps = [d for d in self.engine.get_active_deployments() if d.tenant_id == "t1"]
        self.assertEqual(len(deps), 2)

    def test_upgrade_history_tracking(self):
        d = EditionDeployment(deployment_id="dep-hist", edition_type=EditionType.DEDICATED_SAAS, tenant_id="t1", region=RegionId.US_EAST_1, version="1.0")
        self.engine.register_edition(d)
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.0", target_version="1.1", compatible=True))
        self.engine.register_version_compatibility(VersionCompatibility(source_version="1.1", target_version="1.2", compatible=True))
        
        self.engine.execute_zero_downtime_upgrade("dep-hist", "1.1")
        self.engine.execute_zero_downtime_upgrade("dep-hist", "1.2")
        
        upgrades = [u for u in self.engine._upgrades.values() if u.deployment_id == "dep-hist"]
        self.assertEqual(len(upgrades), 2)
        self.assertTrue(all(u.phase == UpgradePhase.COMPLETE for u in upgrades))

    def test_get_deployment_not_found_raises(self):
        with self.assertRaisesRegex(KeyError, "not found"):
            self.engine.get_deployment("dep-not-found")

    def test_check_upgrade_path_not_found_raises(self):
        with self.assertRaisesRegex(ValueError, "No compatibility path"):
            self.engine.check_upgrade_path("1.0", "9.9")

    def test_advance_upgrade_phase_not_found_raises(self):
        with self.assertRaisesRegex(KeyError, "not found"):
            self.engine.advance_upgrade_phase("upg-not-found")

    def test_rollback_upgrade_not_found_raises(self):
        with self.assertRaisesRegex(KeyError, "not found"):
            self.engine.rollback_upgrade("upg-not-found")

    def test_execute_zero_downtime_upgrade_invalid_strategy(self):
        d = EditionDeployment(
            deployment_id="dep-invalid-strat",
            edition_type=EditionType.DEDICATED_SAAS,
            tenant_id="t1",
            region=RegionId.US_EAST_1,
            version="1.0.0",
            upgrade_strategy=UpgradeStrategy.EXPAND_CONTRACT
        )
        self.engine.register_edition(d)
        with self.assertRaisesRegex(ValueError, "Zero downtime requires"):
            self.engine.execute_zero_downtime_upgrade("dep-invalid-strat", "1.1.0")

if __name__ == '__main__':
    unittest.main()
