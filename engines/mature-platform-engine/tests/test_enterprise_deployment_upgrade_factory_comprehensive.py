import unittest
from typing import Dict, Any

from elmos_mature_platform.types import (
    EditionType, UpgradePhase, EditionProvisioningSpec,
    EditionUpgradeCampaign, EditionDeployment
)
from elmos_mature_platform.enterprise_deployment_upgrade_factory_engine import EnterpriseDeploymentUpgradeFactoryEngine

class TestEnterpriseDeploymentUpgradeFactoryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EnterpriseDeploymentUpgradeFactoryEngine()

    def _create_spec(self, spec_id: str, ed_type: EditionType) -> EditionProvisioningSpec:
        spec = EditionProvisioningSpec(
            spec_id=spec_id,
            tenant_id="t1",
            edition_type=ed_type,
            target_region="us-east-1"
        )
        self.engine.create_provisioning_spec(spec)
        return spec

    def test_create_provisioning_spec_success(self):
        spec = EditionProvisioningSpec(spec_id="spec-1", tenant_id="t1", edition_type=EditionType.MULTITENANT_SAAS, target_region="us-east-1")
        res = self.engine.create_provisioning_spec(spec)
        self.assertEqual(res, "spec-1")
        self.assertIn("spec-1", self.engine.specs)

    def test_create_provisioning_spec_missing_id(self):
        spec = EditionProvisioningSpec(spec_id="", tenant_id="t1", edition_type=EditionType.MULTITENANT_SAAS, target_region="us-east-1")
        with self.assertRaises(ValueError):
            self.engine.create_provisioning_spec(spec)

    def test_provision_edition_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.provision_edition("nonexistent")

    def test_provision_edition_air_gapped(self):
        self._create_spec("spec-air", EditionType.AIR_GAPPED)
        dep = self.engine.provision_edition("spec-air")
        self.assertTrue(dep.network_isolated)
        self.assertEqual(dep.max_tenants, 1)

    def test_provision_edition_sovereign(self):
        spec = EditionProvisioningSpec(spec_id="spec-sov", tenant_id="t1", edition_type=EditionType.PRIVATE_SOVEREIGN, target_region="eu-central-1")
        self.engine.create_provisioning_spec(spec)
        dep = self.engine.provision_edition("spec-sov")
        self.assertEqual(dep.data_residency_region, "eu-central-1")
        self.assertFalse(dep.network_isolated)

    def test_provision_edition_multitenant(self):
        self._create_spec("spec-multi", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("spec-multi")
        self.assertEqual(dep.max_tenants, 100)

    def test_create_upgrade_campaign_success(self):
        camp = EditionUpgradeCampaign(campaign_id="camp-1", name="Upgrade V2", target_version="2.0.0")
        res = self.engine.create_upgrade_campaign(camp)
        self.assertEqual(res, "camp-1")
        self.assertEqual(self.engine.campaigns["camp-1"].status, "pending")

    def test_create_upgrade_campaign_missing_id(self):
        camp = EditionUpgradeCampaign(campaign_id="", name="Upgrade V2", target_version="2.0.0")
        with self.assertRaises(ValueError):
            self.engine.create_upgrade_campaign(camp)

    def test_add_deployment_to_campaign_not_found_campaign(self):
        with self.assertRaises(ValueError):
            self.engine.add_deployment_to_campaign("c1", "d1")

    def test_add_deployment_to_campaign_not_found_deployment(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        with self.assertRaises(ValueError):
            self.engine.add_deployment_to_campaign("c1", "d1")

    def test_add_deployment_to_campaign_invalid_edition(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0", allowed_editions=[EditionType.AIR_GAPPED])
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        with self.assertRaises(ValueError):
            self.engine.add_deployment_to_campaign("c1", dep.deployment_id)

    def test_add_deployment_to_campaign_success(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        self.assertIn(dep.deployment_id, self.engine.campaigns["c1"].target_deployments)

    def test_start_upgrade_campaign_success(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        res = self.engine.start_upgrade_campaign("c1")
        self.assertEqual(res.status, "in_progress")

    def test_start_upgrade_campaign_invalid_state(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self.engine.start_upgrade_campaign("c1")
        with self.assertRaises(ValueError):
            self.engine.start_upgrade_campaign("c1")

    def test_execute_phase_invalid_ids(self):
        with self.assertRaises(ValueError):
            self.engine.execute_deployment_upgrade_phase("c", "d", UpgradePhase.PRE_CHECK)

    def test_execute_phase_deployment_not_in_campaign(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        with self.assertRaises(ValueError):
            self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)

    def test_execute_phase_success_initial(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        
        rec = self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)
        self.assertEqual(rec.phase, UpgradePhase.PRE_CHECK)
        self.assertEqual(rec.from_version, "1.0.0")
        self.assertEqual(rec.to_version, "2.0")

    def test_execute_phase_success_update(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        
        self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)
        rec = self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.BACKUP)
        self.assertEqual(rec.phase, UpgradePhase.BACKUP)

    def test_complete_upgrade_no_record(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        with self.assertRaises(ValueError):
            self.engine.complete_deployment_upgrade("c1", dep.deployment_id, True)

    def test_complete_upgrade_success(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        
        self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)
        rec = self.engine.complete_deployment_upgrade("c1", dep.deployment_id, True)
        
        self.assertTrue(rec.success)
        self.assertEqual(rec.phase, UpgradePhase.COMPLETE)
        self.assertEqual(dep.version, "2.0")
        self.assertEqual(dep.previous_version, "1.0.0")

    def test_complete_upgrade_failure_no_rollback(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0", rollback_on_failure=False)
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        
        self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)
        rec = self.engine.complete_deployment_upgrade("c1", dep.deployment_id, False, "error")
        
        self.assertFalse(rec.success)
        self.assertEqual(rec.error_message, "error")
        self.assertEqual(dep.version, "1.0.0")
        self.assertFalse(rec.rollback_performed)

    def test_complete_upgrade_failure_with_rollback(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0", rollback_on_failure=True)
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        # manually advance version to simulate mid-upgrade failure
        dep.previous_version = "1.0.0"
        dep.version = "1.5.0"
        
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        self.engine.execute_deployment_upgrade_phase("c1", dep.deployment_id, UpgradePhase.PRE_CHECK)
        
        rec = self.engine.complete_deployment_upgrade("c1", dep.deployment_id, False, "error")
        
        self.assertTrue(rec.rollback_performed)
        self.assertEqual(dep.version, "1.0.0")

    def test_rollback_invalid_ids(self):
        with self.assertRaises(ValueError):
            self.engine.rollback_deployment("c", "d")

    def test_rollback_no_record(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        dep = self.engine.provision_edition("s1")
        self.engine.add_deployment_to_campaign("c1", dep.deployment_id)
        with self.assertRaises(ValueError):
            self.engine.rollback_deployment("c1", dep.deployment_id)

    def test_get_campaign_progress_empty(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        prog = self.engine.get_campaign_progress("c1")
        self.assertEqual(prog["total"], 0)
        self.assertEqual(prog["percentage"], 0.0)

    def test_get_campaign_progress_mixed(self):
        camp = EditionUpgradeCampaign(campaign_id="c1", name="N", target_version="2.0")
        self.engine.create_upgrade_campaign(camp)
        
        # d1: completed
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        d1 = self.engine.provision_edition("s1").deployment_id
        self.engine.add_deployment_to_campaign("c1", d1)
        self.engine.execute_deployment_upgrade_phase("c1", d1, UpgradePhase.PRE_CHECK)
        self.engine.complete_deployment_upgrade("c1", d1, True)
        
        # d2: failed, no rollback (so failed in progress calculation)
        self._create_spec("s2", EditionType.MULTITENANT_SAAS)
        d2 = self.engine.provision_edition("s2").deployment_id
        self.engine.add_deployment_to_campaign("c1", d2)
        self.engine.execute_deployment_upgrade_phase("c1", d2, UpgradePhase.PRE_CHECK)
        self.engine.complete_deployment_upgrade("c1", d2, False) # It will auto rollback since default is True. Let's see.
        
        # d3: in progress
        self._create_spec("s3", EditionType.MULTITENANT_SAAS)
        d3 = self.engine.provision_edition("s3").deployment_id
        self.engine.add_deployment_to_campaign("c1", d3)
        self.engine.execute_deployment_upgrade_phase("c1", d3, UpgradePhase.PRE_CHECK)
        
        prog = self.engine.get_campaign_progress("c1")
        self.assertEqual(prog["total"], 3)
        self.assertEqual(prog["completed"], 1)
        self.assertEqual(prog["failed"], 1)
        self.assertEqual(prog["in_progress"], 1)
        self.assertAlmostEqual(prog["percentage"], 33.33333333333333)

    def test_get_edition_matrix_report(self):
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        self.engine.provision_edition("s1")
        self._create_spec("s2", EditionType.AIR_GAPPED)
        d2 = self.engine.provision_edition("s2")
        self.engine.decommission_deployment(d2.deployment_id)
        
        rep = self.engine.get_edition_matrix_report()
        self.assertEqual(rep["total"], 2)
        self.assertEqual(rep["active_count"], 1)
        self.assertEqual(rep["inactive_count"], 1)
        self.assertEqual(rep["by_edition_type"][EditionType.MULTITENANT_SAAS.value], 1)
        self.assertEqual(rep["by_edition_type"][EditionType.AIR_GAPPED.value], 1)
        self.assertEqual(rep["by_version"]["1.0.0"], 2)

    def test_decommission_deployment(self):
        self._create_spec("s1", EditionType.MULTITENANT_SAAS)
        d1 = self.engine.provision_edition("s1")
        self.assertTrue(d1.is_active)
        d2 = self.engine.decommission_deployment(d1.deployment_id)
        self.assertFalse(d2.is_active)

    def test_decommission_deployment_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.decommission_deployment("d")

if __name__ == '__main__':
    unittest.main()
