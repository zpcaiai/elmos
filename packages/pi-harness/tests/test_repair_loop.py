from __future__ import annotations

import unittest

from elmos_pi_harness.repair import (
    CounterexampleShrinker,
    FailureClassifier,
    RepairProposal,
    SelfHealingController,
    admit_repair,
)


class TestRepairLoop(unittest.TestCase):
    def test_admit_repair_blocks_unapproved_or_unverified(self) -> None:
        p = RepairProposal("p1", "TEST_FAILURE", ("src/app.py",), "hash-123", requires_approval=True)
        res = admit_repair(p, verification_passed=False, approved=True)
        self.assertFalse(res["admitted"])
        self.assertIn("verification_not_passed", res["blockers"])

        res2 = admit_repair(p, verification_passed=True, approved=False)
        self.assertFalse(res2["admitted"])
        self.assertIn("approval_required", res2["blockers"])

        res3 = admit_repair(p, verification_passed=True, approved=True)
        self.assertTrue(res3["admitted"])

    def test_failure_classifier(self) -> None:
        syntax_err = 'File "src/main.py", line 42\n  def foo(\nSyntaxError: unexpected EOF while parsing'
        c = FailureClassifier.classify(syntax_err)
        self.assertEqual(c.failure_class, "SYNTAX_ERROR")
        self.assertTrue(c.is_retryable)
        self.assertIn("src/main.py", c.suspect_files)

        test_err = 'AssertionError: expected 200 but got 500\nFile "tests/test_api.py", line 12'
        c2 = FailureClassifier.classify(test_err)
        self.assertEqual(c2.failure_class, "TEST_FAILURE")
        self.assertTrue(c2.is_retryable)

        policy_err = "PolicyDeniedError: capability 'network.egress' is denied by upper policy"
        c3 = FailureClassifier.classify(policy_err)
        self.assertEqual(c3.failure_class, "POLICY_DENIAL")
        self.assertFalse(c3.is_retryable)

        stale_err = "StaleGenerationError: generation 1 is older than active 2"
        c4 = FailureClassifier.classify(stale_err)
        self.assertEqual(c4.failure_class, "STALE_GENERATION")
        self.assertFalse(c4.is_retryable)

    def test_counterexample_shrinker(self) -> None:
        long_output = "\n".join([f"line {i} normal info" for i in range(100)]) + "\nAssertionError: failed!\n" + "\n".join([f"line {i} post" for i in range(20)])
        shrunk = CounterexampleShrinker.shrink(long_output, max_lines=20)
        self.assertLessEqual(len(shrunk.splitlines()), 25)
        self.assertIn("AssertionError: failed!", shrunk)

    def test_self_healing_controller_flow(self) -> None:
        ctrl = SelfHealingController(max_attempts=3, initial_generation=1)
        self.assertTrue(ctrl.can_repair)
        self.assertEqual(ctrl.remaining_budget, 3)

        raw = 'File "src/core.py", line 10\nAssertionError: 1 != 2'
        att1 = ctrl.record_failure(raw, "Fix calculations")
        self.assertEqual(att1.attempt_number, 1)
        self.assertEqual(att1.executor_generation, 2)
        self.assertEqual(ctrl.current_generation, 2)
        self.assertEqual(ctrl.remaining_budget, 2)
        self.assertIn("Auto-Repair Attempt 1/3", att1.repair_prompt)
        self.assertIn("src/core.py", att1.repair_prompt)

        ctrl.record_failure(raw, "Fix calculations")
        self.assertEqual(ctrl.remaining_budget, 1)

        ctrl.record_failure(raw, "Fix calculations")
        self.assertEqual(ctrl.remaining_budget, 0)
        self.assertFalse(ctrl.can_repair)


if __name__ == "__main__":
    unittest.main()
