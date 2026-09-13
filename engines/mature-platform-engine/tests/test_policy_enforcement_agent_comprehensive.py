"""Comprehensive test suite for PolicyEnforcementAgentEngine (Batch 42 - Skill 1419)."""

import unittest

from elmos_mature_platform.policy_enforcement_agent_engine import (
    PolicyEnforcementAgentEngine,
)
from elmos_mature_platform.types import (
    PolicyAgentDecision,
)


class TestPolicyEnforcementAgentComprehensive(unittest.TestCase):
    """Rigorous tests covering code patch inspection, invariant enforcement, blocking, and human override."""

    def setUp(self) -> None:
        self.engine = PolicyEnforcementAgentEngine()

    def test_evaluate_patch_clean_code_allowed(self) -> None:
        clean_patch = """
        def compute_sum(a: int, b: int) -> int:
            return a + b
        """
        eval_res = self.engine.evaluate_patch(
            agent_id="agent-01",
            task_id="task-01",
            patch_content=clean_patch,
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.ALLOW)
        self.assertEqual(len(eval_res.violations), 0)

    def test_evaluate_patch_critical_eval_exec_blocked(self) -> None:
        malicious_patch = """
        def execute_dynamic(user_input: str):
            eval(user_input)
        """
        eval_res = self.engine.evaluate_patch(
            agent_id="agent-02",
            task_id="task-02",
            patch_content=malicious_patch,
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.BLOCK)
        self.assertTrue(len(eval_res.violations) > 0)
        self.assertEqual(eval_res.violations[0].rule_id, "RULE-SEC-01")

    def test_evaluate_patch_secret_token_leak_blocked(self) -> None:
        secret_patch = """
        GITHUB_TOKEN = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        """
        eval_res = self.engine.evaluate_patch(
            agent_id="agent-03",
            task_id="task-03",
            patch_content=secret_patch,
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.BLOCK)
        self.assertEqual(eval_res.violations[0].rule_id, "RULE-SEC-02")

    def test_evaluate_patch_test_deletion_blocked(self) -> None:
        tamper_patch = """
        @unittest.skip("skipping broken test")
        def test_critical_security():
            pass
        """
        eval_res = self.engine.evaluate_patch(
            agent_id="agent-04",
            task_id="task-04",
            patch_content=tamper_patch,
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.BLOCK)
        self.assertEqual(eval_res.violations[0].rule_id, "RULE-ARCH-01")

    def test_override_decision(self) -> None:
        malicious_patch = "eval('safe_context')"
        eval_res = self.engine.evaluate_patch(
            agent_id="agent-05", task_id="task-05", patch_content=malicious_patch
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.BLOCK)

        with self.assertRaises(ValueError):
            self.engine.override_decision(eval_res.eval_id, approver="", rationale="")

        overridden = self.engine.override_decision(
            eval_res.eval_id,
            approver="sec-lead@company.com",
            rationale="Sandboxed eval execution approved for math expressions.",
        )
        self.assertEqual(overridden.decision, PolicyAgentDecision.OVERRIDE)

    def test_register_custom_rule(self) -> None:
        self.engine.register_policy_rule(
            rule_id="RULE-CORP-01",
            description="Ban raw print statements in production services",
            forbidden_patterns=["print("],
            severity="low",
        )
        eval_res = self.engine.evaluate_patch(
            agent_id="a1", task_id="t1", patch_content="print('debug')"
        )
        self.assertEqual(eval_res.decision, PolicyAgentDecision.FLAG)

    def test_policy_report(self) -> None:
        self.engine.evaluate_patch("a1", "t1", "clean code")
        self.engine.evaluate_patch("a2", "t2", "eval('code')")
        rep = self.engine.get_policy_enforcement_report()
        self.assertEqual(rep["total_evaluations"], 2)
        self.assertEqual(rep["allowed_count"], 1)
        self.assertEqual(rep["blocked_count"], 1)
        self.assertEqual(rep["compliance_pass_rate_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
