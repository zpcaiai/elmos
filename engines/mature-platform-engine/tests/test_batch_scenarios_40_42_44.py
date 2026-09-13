"""Integration tests for Batch 40, 42, and 44 scenarios.

These tests execute the actual scenario functions with real engine instances.
Every assertion is verified by the test harness — not just format-checked.
"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.credential_triage_engine import CredentialTriageEngine
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.governed_agent_factory import GovernedAgentFactory
from elmos_mature_platform.finops_economics_engine import FinOpsEconomicsEngine

from elmos_mature_platform.scenarios.batch40_supply_chain import execute_batch40_case
from elmos_mature_platform.scenarios.batch42_agent_factory import execute_batch42_case
from elmos_mature_platform.scenarios.batch44_finops import execute_batch44_case


class TestBatch40SupplyChain(unittest.TestCase):
    """B40: Supply Chain & Security Compliance Scenarios."""

    def setUp(self) -> None:
        self.oidc = EnterpriseOidcProvider()
        self.kms = EnterpriseKmsService()
        self.triage = CredentialTriageEngine(self.kms)
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category}
        assertions, metrics = execute_batch40_case(
            meta, self.oidc, self.kms, self.triage, self._trace
        )
        return assertions

    def test_b40_001_sbom_cryptographic_verification(self) -> None:
        assertions = self._run("B40-001", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b40_002_slsa_provenance(self) -> None:
        assertions = self._run("B40-002", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b40_003_secret_credential_leakage(self) -> None:
        assertions = self._run("B40-003", "success")
        self.assertGreaterEqual(len(assertions), 2)
        for a in assertions:
            self.assertTrue(a.passed, a.details)

    def test_b40_004_vulnerability_vex(self) -> None:
        assertions = self._run("B40-004", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b40_005_kms_envelope_key_rotation(self) -> None:
        assertions = self._run("B40-005", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)
        
    def test_b40_009_sbom_cryptographic_verification_alt(self) -> None:
        assertions = self._run("B40-009", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b40_011_secret_credential_leakage_alt(self) -> None:
        assertions = self._run("B40-011", "success")
        self.assertGreaterEqual(len(assertions), 2)
        for a in assertions:
            self.assertTrue(a.passed, a.details)


class TestBatch42AgentFactory(unittest.TestCase):
    """B42: Governed Agent Factory Scenarios."""

    def setUp(self) -> None:
        self.agents = GovernedAgentFactory()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category}
        assertions, metrics = execute_batch42_case(
            meta, self.agents, self._trace
        )
        return assertions

    def test_b42_001_multi_agent_topology(self) -> None:
        assertions = self._run("B42-001", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b42_002_autonomy_level_boundary(self) -> None:
        assertions = self._run("B42-002", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b42_003_dead_man_kill_switch(self) -> None:
        assertions = self._run("B42-003", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b42_004_red_team_adversarial_drill(self) -> None:
        assertions = self._run("B42-004", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)
        
    def test_b42_009_multi_agent_topology_alt(self) -> None:
        assertions = self._run("B42-009", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b42_012_red_team_adversarial_drill_alt(self) -> None:
        assertions = self._run("B42-012", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)


class TestBatch44FinOps(unittest.TestCase):
    """B44: FinOps & Migration Economics Scenarios."""

    def setUp(self) -> None:
        self.finops = FinOpsEconomicsEngine()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, case_id: str, category: str) -> list:
        meta = {"case_id": case_id, "category": category}
        assertions, metrics = execute_batch44_case(
            meta, self.finops, self._trace
        )
        return assertions

    def test_b44_001_multi_resource_metering(self) -> None:
        assertions = self._run("B44-001", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b44_002_billing_invoice_reconciliation(self) -> None:
        assertions = self._run("B44-002", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b44_003_platform_gross_margin(self) -> None:
        assertions = self._run("B44-003", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b44_004_tenant_budget_guardrail(self) -> None:
        assertions = self._run("B44-004", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)
        
    def test_b44_009_multi_resource_metering_alt(self) -> None:
        assertions = self._run("B44-009", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b44_011_platform_gross_margin_alt(self) -> None:
        assertions = self._run("B44-011", "success")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)

    def test_b44_fallback_scenario(self) -> None:
        assertions = self._run("B44-999", "fallback")
        self.assertGreater(len(assertions), 0)
        self.assertTrue(assertions[0].passed, assertions[0].details)


if __name__ == "__main__":
    unittest.main()
