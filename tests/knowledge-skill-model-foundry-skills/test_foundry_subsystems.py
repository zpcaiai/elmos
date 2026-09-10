"""Comprehensive test suite for Knowledge-Skill-Model Foundry Subsystems."""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines/knowledge-skill-model-foundry-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_foundry.subsystems.ast_codemod_toolkit import ASTCodemodToolkit  # noqa: E402
from elmos_foundry.subsystems.polyglot_sql_transpiler import PolyglotSQLTranspiler  # noqa: E402
from elmos_foundry.subsystems.prompt_guard_engine import PromptGuardEngine  # noqa: E402
from elmos_foundry.subsystems.concurrency_deadlock_engine import ConcurrencyDeadlockEngine  # noqa: E402
from elmos_foundry.subsystems.spdx_cyclonedx_license_engine import SPDXCycloneDXLicenseEngine  # noqa: E402
from elmos_foundry.subsystems.metamorphic_fuzz_engine import MetamorphicFuzzEngine  # noqa: E402
from elmos_foundry.subsystems.formal_contract_synthesizer import FormalContractSynthesizer  # noqa: E402
from elmos_foundry.subsystems.model_routing_optimizer import ModelRoutingOptimizer  # noqa: E402
from elmos_foundry.subsystems.evaluation_consensus_engine import EvaluationConsensusEngine  # noqa: E402


class FoundrySubsystemsTests(unittest.TestCase):
    def test_ast_codemod_and_sql_transpiler(self) -> None:
        ast_eng = ASTCodemodToolkit("tenant-foundry-01")
        sql_eng = PolyglotSQLTranspiler("tenant-foundry-01")

        rule1 = ast_eng.execute_rule_slice_1({"id": "AST-01", "pattern": "def foo() -> None", "confidence": 0.99})
        sql_rule1 = sql_eng.execute_rule_slice_1({"id": "SQL-01", "pattern": "SELECT * FROM dual", "confidence": 0.95})

        self.assertTrue(rule1.is_enabled)
        self.assertEqual(rule1.rule_id, "AST-01")
        self.assertTrue(len(rule1.fingerprint()) == 64)

        self.assertTrue(sql_rule1.is_enabled)
        self.assertEqual(sql_rule1.rule_id, "SQL-01")
        self.assertTrue(sql_eng.compute_audit_merkle_digest().startswith("sha256:"))

    def test_prompt_guard_and_concurrency_deadlock(self) -> None:
        guard = PromptGuardEngine("tenant-foundry-02")
        deadlock = ConcurrencyDeadlockEngine("tenant-foundry-02")

        g_rule = guard.execute_rule_slice_1({"id": "SEC-PROMPT-01", "pattern": "ignore previous instructions", "confidence": 0.99})
        d_rule = deadlock.execute_rule_slice_1({"id": "LOCK-ORDER-01", "pattern": "lock(A) -> lock(B)", "confidence": 0.97})

        self.assertTrue(g_rule.is_enabled)
        self.assertTrue(d_rule.is_enabled)
        self.assertTrue(guard.compute_audit_merkle_digest().startswith("sha256:"))
        self.assertTrue(deadlock.compute_audit_merkle_digest().startswith("sha256:"))

    def test_spdx_license_and_metamorphic_fuzz(self) -> None:
        spdx = SPDXCycloneDXLicenseEngine("tenant-foundry-03")
        fuzz = MetamorphicFuzzEngine("tenant-foundry-03")

        s_rule = spdx.execute_rule_slice_1({"id": "LIC-01", "pattern": "Apache-2.0 AND MIT", "confidence": 1.0})
        m_rule = fuzz.execute_rule_slice_1({"id": "FUZZ-01", "pattern": "f(x) == f(rev(rev(x)))", "confidence": 0.96})

        self.assertTrue(s_rule.is_enabled)
        self.assertTrue(m_rule.is_enabled)
        self.assertTrue(spdx.compute_audit_merkle_digest().startswith("sha256:"))
        self.assertTrue(fuzz.compute_audit_merkle_digest().startswith("sha256:"))

    def test_formal_contract_model_routing_consensus(self) -> None:
        contract = FormalContractSynthesizer("tenant-foundry-04")
        router = ModelRoutingOptimizer("tenant-foundry-04")
        consensus = EvaluationConsensusEngine("tenant-foundry-04")

        c_rule = contract.execute_rule_slice_1({"id": "CONTRACT-01", "pattern": "requires x > 0 ensures result >= x", "confidence": 0.99})
        r_rule = router.execute_rule_slice_1({"id": "ROUTE-01", "pattern": "latency < 200ms AND cost < 0.01", "confidence": 0.94})
        e_rule = consensus.execute_rule_slice_1({"id": "CONSENSUS-01", "pattern": "majority_vote(v1, v2, v3)", "confidence": 0.98})

        self.assertTrue(c_rule.is_enabled)
        self.assertTrue(r_rule.is_enabled)
        self.assertTrue(e_rule.is_enabled)
        self.assertTrue(contract.compute_audit_merkle_digest().startswith("sha256:"))
        self.assertTrue(router.compute_audit_merkle_digest().startswith("sha256:"))
        self.assertTrue(consensus.compute_audit_merkle_digest().startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
