import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.credential_triage_engine import CredentialTriageEngine
from elmos_mature_platform.finops_economics_engine import FinOpsEconomicsEngine
from elmos_mature_platform.governed_agent_factory import GovernedAgentFactory
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.types import AgentAutonomyLevel
from elmos_mature_platform.scenarios.cross_cutting_security_governance import (
    execute_cross_cutting_security_governance,
)

class BaseSecurityGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.oidc = EnterpriseOidcProvider()
        self.kms = EnterpriseKmsService()
        self.triage = CredentialTriageEngine()
        self.agents = GovernedAgentFactory()
        self.finops = FinOpsEconomicsEngine()
        self.trace_log = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str, skill_code: str):
        meta = {"case_id": case_id, "category": category, "skill_code": skill_code}
        return execute_cross_cutting_security_governance(
            meta, self.oidc, self.kms, self.triage, self.agents, self.finops, self._trace
        )

class TestScenarioU018SupplyChain(BaseSecurityGovernanceTest):
    def test_success_sbom_parsing(self):
        assertions, metrics = self._run("X-U018-001", "success", "U018")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertIn("slsa_level", metrics)
        self.assertEqual(metrics["slsa_level"], 3.0)

    def test_negative_cve_blocked(self):
        assertions, _ = self._run("X-U018-002", "negative", "U018")
        self.assertTrue(all(a.passed for a in assertions))

    def test_security_tamper_detection(self):
        assertions, _ = self._run("X-U018-003", "security", "U018")
        self.assertTrue(all(a.passed for a in assertions))

    def test_boundary_deep_parsing(self):
        assertions, _ = self._run("X-U018-004", "boundary", "U018")
        self.assertTrue(all(a.passed for a in assertions))

class TestScenarioU019ComplianceAudit(BaseSecurityGovernanceTest):
    def test_success_audit_ledger(self):
        # We need to simulate audit writes so the ledger isn't empty, depending on how KMS works.
        assertions, metrics = self._run("X-U019-001", "success", "U019")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertIn("audit_records_verified", metrics)

    def test_negative_tamper_blocked(self):
        assertions, _ = self._run("X-U019-002", "negative", "U019")
        self.assertTrue(all(a.passed for a in assertions))

    def test_evidence_tamper_hash_break(self):
        assertions, _ = self._run("X-U019-003", "evidence-tamper", "U019")
        self.assertTrue(all(a.passed for a in assertions))

class TestScenarioU020KnowledgeIsolation(BaseSecurityGovernanceTest):
    def test_success_tenant_isolation(self):
        assertions, metrics = self._run("X-U020-001", "success", "U020")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertIn("groundedness_score", metrics)
        self.assertGreater(metrics["groundedness_score"], 0.9)

    def test_negative_prompt_injection(self):
        assertions, _ = self._run("X-U020-002", "negative", "U020")
        self.assertTrue(all(a.passed for a in assertions))

    def test_dependency_failure_failover(self):
        assertions, _ = self._run("X-U020-003", "dependency-failure", "U020")
        self.assertTrue(all(a.passed for a in assertions))

class TestScenarioU021AgentGovernance(BaseSecurityGovernanceTest):
    def test_success_agent_authorization(self):
        assertions, metrics = self._run("X-U021-001", "success", "U021")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertEqual(metrics.get("active_agents"), 1.0)
        self.assertIn("agent-gov-x-u021-001", self.agents.agents)

    def test_negative_destructive_blocked(self):
        assertions, _ = self._run("X-U021-002", "negative", "U021")
        self.assertTrue(all(a.passed for a in assertions))

    def test_security_kill_switch(self):
        assertions, _ = self._run("X-U021-003", "security", "U021")
        self.assertTrue(all(a.passed for a in assertions))

    def test_boundary_step_limit(self):
        assertions, _ = self._run("X-U021-004", "boundary", "U021")
        self.assertTrue(all(a.passed for a in assertions))

class TestScenarioU022FinopsBudget(BaseSecurityGovernanceTest):
    def test_success_budget_guardrail(self):
        assertions, metrics = self._run("X-U022-001", "success", "U022")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertIn("spend_percentage", metrics)

    def test_boundary_budget_exceeded(self):
        assertions, _ = self._run("X-U022-002", "boundary", "U022")
        self.assertTrue(all(a.passed for a in assertions))

    def test_negative_quota_rejection(self):
        assertions, _ = self._run("X-U022-003", "negative", "U022")
        self.assertTrue(all(a.passed for a in assertions))

    def test_dependency_failure_failover(self):
        assertions, _ = self._run("X-U022-004", "dependency-failure", "U022")
        self.assertTrue(all(a.passed for a in assertions))

class TestScenarioU023ApiSdkCompat(BaseSecurityGovernanceTest):
    def test_success_contracts(self):
        assertions, metrics = self._run("X-U023-001", "success", "U023")
        self.assertTrue(all(a.passed for a in assertions))
        self.assertEqual(metrics.get("schema_conformance_pct"), 100.0)

    def test_negative_invalid_event(self):
        assertions, _ = self._run("X-U023-002", "negative", "U023")
        self.assertTrue(all(a.passed for a in assertions))

    def test_security_hmac(self):
        assertions, _ = self._run("X-U023-003", "security", "U023")
        self.assertTrue(all(a.passed for a in assertions))

class TestDirectEngines(BaseSecurityGovernanceTest):
    def test_agent_authorization_logic(self):
        agent_id = "test-agent-auth"
        self.agents.register_agent(agent_id, "DevAgent", "Developer", AgentAutonomyLevel.L1_SUGGESTION)
        
        ok, msg = self.agents.authorize_tool_call(agent_id, "read_file", "tenant1")
        self.assertTrue(ok)
        
        ok, msg = self.agents.authorize_tool_call(agent_id, "delete_production_database", "tenant1")
        self.assertFalse(ok)
        self.assertIn("E_TOOL_UNREGISTERED", msg)

    def test_agent_kill_switch_logic(self):
        agent_id = "test-agent-kill"
        self.agents.register_agent(agent_id, "RogueAgent", "Hacker", AgentAutonomyLevel.L4_FULL_AUTONOMOUS)
        
        kill_event = self.agents.trigger_kill_switch(agent_id, "Rogue detected", "sec_officer")
        self.assertTrue(kill_event.confirmed_killed)
        self.assertEqual(kill_event.target_agent_id, agent_id)

    def test_finops_budget_logic(self):
        tenant = "tenant-budget"
        self.finops.set_budget(tenant, 100.0)
        
        self.finops.record_usage(tenant, "cpu", 9900.0) # 9900.0 * 0.01 = 99.0
        ok, msg, pct = self.finops.check_budget_guardrail(tenant)
        self.assertTrue(ok)
        self.assertAlmostEqual(pct, 99.0)
        
        self.finops.record_usage(tenant, "cpu", 200.0) # 200.0 * 0.01 = 2.0 -> total 101.0
        ok, msg, pct = self.finops.check_budget_guardrail(tenant)
        self.assertFalse(ok)
        self.assertAlmostEqual(pct, 101.0)

    def test_kms_audit_ledger_integrity(self):
        self.kms.create_key("test_key")
        self.kms.create_key("test_key2")
        valid, count, msg = self.kms.verify_audit_ledger_integrity()
        self.assertTrue(valid)
        self.assertEqual(count, 3)

if __name__ == "__main__":
    unittest.main()
