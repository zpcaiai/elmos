import unittest
from elmos_mature_platform.dedicated_saas_edition_engine import DedicatedSaasEditionEngine
from elmos_mature_platform.types import (
    DedicatedSaasAuditRecord,
    DedicatedSaasConfig,
    DedicatedSaasIsolationLevel,
    DedicatedSaasStatus,
)


class TestDedicatedSaasEditionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = DedicatedSaasEditionEngine()

    def test_provision_and_activate_edition(self):
        cfg = DedicatedSaasConfig(
            edition_id="",
            customer_id="cust-enterprise-1",
            customer_name="Acme Corp",
            custom_domain="portal.acme-corp.com",
            isolation_level=DedicatedSaasIsolationLevel.DEDICATED_CLUSTER,
        )
        ed_id = self.engine.provision_dedicated_saas(cfg)
        self.assertTrue(bool(ed_id))
        self.assertEqual(cfg.status, DedicatedSaasStatus.PROVISIONING)

        activated = self.engine.activate_edition(ed_id)
        self.assertEqual(activated.status, DedicatedSaasStatus.ACTIVE)

    def test_byok_and_vpc_peering_configuration(self):
        cfg = DedicatedSaasConfig(
            edition_id="ded-byok-1",
            customer_id="cust-bank-99",
            customer_name="Bank 99",
            custom_domain="secure.bank.com",
            isolation_level=DedicatedSaasIsolationLevel.HARDWARE_ISOLATED,
        )
        self.engine.provision_dedicated_saas(cfg)

        self.engine.configure_byok("ded-byok-1", "arn:aws:kms:us-east-1:123456789012:key/byok-key-01")
        self.assertEqual(cfg.byok_key_arn, "arn:aws:kms:us-east-1:123456789012:key/byok-key-01")

        self.engine.configure_vpc_peering("ded-byok-1", "pcx-0123456789abcdef0")
        self.assertEqual(cfg.vpc_peering_id, "pcx-0123456789abcdef0")

    def test_record_audit_and_verify_health(self):
        cfg = DedicatedSaasConfig(
            edition_id="ded-audit-1",
            customer_id="cust-health-1",
            customer_name="City Hospital",
            custom_domain="ehr.hospital.org",
            isolation_level=DedicatedSaasIsolationLevel.DEDICATED_CLUSTER,
        )
        ed_id = self.engine.provision_dedicated_saas(cfg)
        self.engine.activate_edition(ed_id)
        self.engine.configure_byok(ed_id, "arn:kms:health-key")

        audit = DedicatedSaasAuditRecord(
            audit_id="",
            edition_id="",
            audit_type="network_isolation",
            passed=True,
            details="Zero cross-tenant traffic observed",
        )
        self.engine.record_isolation_audit(ed_id, audit)

        health = self.engine.verify_isolation_health(ed_id)
        self.assertTrue(health["is_healthy"])
        self.assertEqual(health["passed_audits"], 1)
        self.assertTrue(health["byok_configured"])

    def test_suspend_and_fleet_report(self):
        cfg = DedicatedSaasConfig(
            edition_id="ded-susp-1",
            customer_id="cust-churn-1",
            customer_name="Churn Corp",
            custom_domain="app.churn.io",
            isolation_level=DedicatedSaasIsolationLevel.VPC_PEERED,
        )
        ed_id = self.engine.provision_dedicated_saas(cfg)
        self.engine.suspend_edition(ed_id, reason="Account migration complete")
        self.assertEqual(cfg.status, DedicatedSaasStatus.SUSPENDED)

        fleet = self.engine.get_dedicated_saas_fleet_report()
        self.assertEqual(fleet["total_deployments"], 1)
        self.assertEqual(fleet["active_deployments"], 0)


if __name__ == "__main__":
    unittest.main()
