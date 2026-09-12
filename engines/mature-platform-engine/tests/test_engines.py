"""Unit tests for Elmos Mature Platform Engine components."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    RegionId,
    AgentAutonomyLevel,
    FaultType,
    FaultDescriptor,
    DrPlan,
    TriageStatus,
)
from elmos_mature_platform.cross_region_simulation import CrossRegionSimulationEnvironment
from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.chaos_fault_engine import EnterpriseChaosEngine
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
from elmos_mature_platform.credential_triage_engine import CredentialTriageEngine
from elmos_mature_platform.disaster_recovery_runner import DisasterRecoveryRunner
from elmos_mature_platform.governed_agent_factory import GovernedAgentFactory
from elmos_mature_platform.finops_economics_engine import FinOpsEconomicsEngine


class TestCrossRegionEnvironment(unittest.TestCase):
    def setUp(self) -> None:
        self.env = CrossRegionSimulationEnvironment()

    def test_default_topology(self) -> None:
        self.assertEqual(len(self.env.regions), 3)
        self.assertIn(RegionId.US_EAST_1, self.env.regions)
        self.assertTrue(self.env.regions[RegionId.US_EAST_1].is_primary)

    def test_isolation_and_healing(self) -> None:
        self.env.isolate_region(RegionId.US_EAST_1)
        self.assertIn(RegionId.EU_WEST_1, self.env.regions[RegionId.US_EAST_1].partitioned_peers)

        # Heal partition
        self.env.heal_partition(RegionId.US_EAST_1)
        self.assertNotIn(RegionId.EU_WEST_1, self.env.regions[RegionId.US_EAST_1].partitioned_peers)


class TestEnterpriseOidcProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.oidc = EnterpriseOidcProvider()

    def test_token_mint_and_validation(self) -> None:
        res = self.oidc.mint_token(
            tenant_id="tenant-alpha",
            subject="user-admin",
            roles=["platform_admin"],
        )
        self.assertIsNotNone(res.token)
        self.assertEqual(res.claims.iss, self.oidc.issuer)

        valid, validated_claims, msg = self.oidc.verify_token(res.token)
        self.assertTrue(valid, msg)
        self.assertIsNotNone(validated_claims)
        self.assertEqual(validated_claims.sub, "user-admin")

    def test_token_revocation(self) -> None:
        res = self.oidc.mint_token(
            tenant_id="tenant-alpha",
            subject="user-temp",
            roles=["tenant_operator"],
        )
        self.oidc.revoke_token(res.claims.jti, tenant_id="tenant-alpha", actor="admin")
        valid, _, msg = self.oidc.verify_token(res.token)
        self.assertFalse(valid)
        self.assertIn("REVOKED", msg)


class TestEnterpriseKmsService(unittest.TestCase):
    def setUp(self) -> None:
        self.kms = EnterpriseKmsService()

    def test_envelope_encrypt_decrypt(self) -> None:
        key_id = "key-patient-data"
        self.kms.create_key(key_id)

        plaintext = b"Sensitive Medical Health Record PHI"
        enc_record = self.kms.envelope_encrypt(key_id, plaintext, tenant_id="health-corp", resource_id="patient-1")
        self.assertIsNotNone(enc_record.ciphertext_b64)

        decrypted = self.kms.envelope_decrypt(enc_record, tenant_id="health-corp", resource_id="patient-1")
        self.assertEqual(decrypted, plaintext)

    def test_cross_tenant_decryption_blocked(self) -> None:
        key_id = "key-tenant-a"
        self.kms.create_key(key_id)
        enc_record = self.kms.envelope_encrypt(key_id, b"Secret Data", tenant_id="tenant-a", resource_id="res-1")

        with self.assertRaises(PermissionError):
            self.kms.envelope_decrypt(enc_record, tenant_id="tenant-b", resource_id="res-1")

    def test_crypto_shred(self) -> None:
        key_id = "key-gdpr-user"
        self.kms.create_key(key_id)
        enc_record = self.kms.envelope_encrypt(key_id, b"Personal Info", tenant_id="tenant-gdpr", resource_id="gdpr-1")

        shredded_count = self.kms.crypto_shred_key(key_id)
        self.assertGreater(shredded_count, 0)

        with self.assertRaises(PermissionError):
            self.kms.envelope_decrypt(enc_record, tenant_id="tenant-gdpr", resource_id="gdpr-1")


class TestChaosFaultEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.env = CrossRegionSimulationEnvironment()
        self.chaos = EnterpriseChaosEngine(self.env)

    def test_inject_fault(self) -> None:
        fault = FaultDescriptor(
            fault_id="fault-net-01",
            fault_type=FaultType.NETWORK_PARTITION,
            target_region=RegionId.AP_SOUTHEAST_1,
            target_node_ids=[],
            parameters={"duration_seconds": 30.0, "blast_radius": 0.33},
        )
        ok = self.chaos.inject_fault(fault)
        self.assertTrue(ok)
        self.assertEqual(len(self.chaos.active_faults), 1)

        healed = self.chaos.clear_fault("fault-net-01")
        self.assertTrue(healed)
        self.assertEqual(len(self.chaos.active_faults), 0)


class TestEnterpriseSloCollector(unittest.TestCase):
    def setUp(self) -> None:
        self.slo = EnterpriseSloCollector()

    def test_metric_and_compliance(self) -> None:
        for _ in range(20):
            self.slo.record_metric_sample("http_request_success_ratio", 1.0)
        self.slo.record_metric_sample("http_request_duration_seconds", 0.045)

        res = self.slo.evaluate_slo("api-availability")
        self.assertTrue(res.is_compliant)
        self.assertEqual(res.actual_percentage, 100.0)

        snap = self.slo.compute_histogram("http_request_success_ratio")
        self.assertEqual(snap.count, 20)
        self.assertEqual(snap.p99, 1.0)


class TestCredentialTriageEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.oidc = EnterpriseOidcProvider()
        self.kms = EnterpriseKmsService()
        self.triage = CredentialTriageEngine(oidc_provider=self.oidc, kms_service=self.kms)

    def test_scan_and_auto_remediation(self) -> None:
        findings = self.triage.scan_content(
            "Config: aws_key = AKIAIOSFODNN7EXAMPLE",
            source_path="config.yaml",
        )
        self.assertGreater(len(findings), 0)
        self.assertEqual(findings[0].secret_type, "AWS_ACCESS_KEY")

        case = self.triage.initiate_triage(findings[0], tenant_id="tenant-alpha")
        self.assertIsNotNone(case)
        self.assertEqual(case.status, TriageStatus.RESOLVED)


class TestDisasterRecoveryRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.env = CrossRegionSimulationEnvironment()
        self.dr = DisasterRecoveryRunner(self.env)

    def test_data_store_reconciliation(self) -> None:
        primary = {"acc-1": b"balance:100", "acc-2": b"balance:200"}
        replica = {"acc-1": b"balance:100", "acc-2": b"balance:200"}

        result = self.dr.reconcile_data_stores(primary, replica)
        self.assertFalse(result.data_loss_detected)
        self.assertEqual(result.primary_root_hash, result.replica_root_hash)
        self.assertEqual(len(result.divergent_keys), 0)

    def test_failover_drill(self) -> None:
        primary = {"k1": b"v1"}
        standby = {"k1": b"v1"}
        plan = DrPlan(
            plan_id="plan-test",
            primary_region=RegionId.US_EAST_1,
            secondary_regions=[RegionId.EU_WEST_1],
            rto_target_seconds=10.0,
            rpo_target_seconds=5.0,
        )
        drill_res = self.dr.execute_disaster_recovery_drill(
            plan=plan,
            source_data=primary,
            replica_data=standby,
        )
        self.assertTrue(drill_res.rto_met)
        self.assertTrue(drill_res.rpo_met)
        self.assertFalse(drill_res.data_reconciliation.data_loss_detected)


class TestGovernedAgentFactory(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = GovernedAgentFactory()

    def test_agent_registration_and_authz(self) -> None:
        agent = self.factory.register_agent(
            agent_id="agent-007",
            name="James",
            role="Intelligence",
            autonomy_level=AgentAutonomyLevel.L2_SUPERVISED,
        )
        self.assertIsNotNone(agent)

        # file_read / read_file should be authorized
        ok, msg = self.factory.authorize_tool_call("agent-007", "file_read", "tenant-1")
        self.assertTrue(ok, msg)
        ok2, msg2 = self.factory.authorize_tool_call("agent-007", "read_file", "tenant-1")
        self.assertTrue(ok2, msg2)

    def test_kill_switch(self) -> None:
        self.factory.register_agent(
            agent_id="agent-rogue",
            name="Rogue",
            role="Worker",
            autonomy_level=AgentAutonomyLevel.L3_BOUNDED_AUTONOMOUS,
        )
        event = self.factory.trigger_kill_switch("agent-rogue", "Unauthorized activity")
        self.assertTrue(event.confirmed_killed)

        # Tool calls should fail after kill
        ok, msg = self.factory.authorize_tool_call("agent-rogue", "file_read", "tenant-1")
        self.assertFalse(ok)
        self.assertIn("KILLED", msg)


class TestFinOpsEconomicsEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.finops = FinOpsEconomicsEngine()

    def test_usage_and_reconciliation(self) -> None:
        self.finops.record_usage("tenant-x", "cpu_hours", 100.0)
        self.finops.record_usage("tenant-x", "egress_gb", 50.0)

        invoices = self.finops.generate_invoice("tenant-x", "2026-09")
        self.assertEqual(len(invoices), 2)

        reconciled, disc, issues = self.finops.reconcile_billing("tenant-x")
        self.assertTrue(reconciled)
        self.assertEqual(disc, 0.0)

    def test_budget_guardrails(self) -> None:
        self.finops.set_budget("tenant-budget", 10.0)
        self.finops.record_usage("tenant-budget", "cpu_hours", 10.0)  # 10 * 0.048 = 0.48
        ok, _, pct = self.finops.check_budget_guardrail("tenant-budget")
        self.assertTrue(ok)

        # Exceed budget
        self.finops.record_usage("tenant-budget", "cpu_hours", 500.0)  # 500 * 0.048 = 24.0 > 10.0
        ok_exceeded, msg, _ = self.finops.check_budget_guardrail("tenant-budget")
        self.assertFalse(ok_exceeded)
        self.assertIn("HARD_LIMIT_REACHED", msg)


if __name__ == "__main__":
    unittest.main()
