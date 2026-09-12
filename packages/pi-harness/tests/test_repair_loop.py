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

    def test_deterministic_repair_strategy(self) -> None:
        from elmos_pi_harness.repair import DeterministicRepairStrategy

        c_syntax = FailureClassifier.classify('SyntaxError: invalid syntax\nFile "test.py", line 1')
        strat_syntax = DeterministicRepairStrategy.recommend(c_syntax)
        self.assertEqual(strat_syntax.action, "APPLY_AST_PARSER_AUTODETECTION")
        self.assertFalse(strat_syntax.requires_human_approval)

        c_policy = FailureClassifier.classify("PolicyDeniedError: capability denied")
        strat_policy = DeterministicRepairStrategy.recommend(c_policy)
        self.assertEqual(strat_policy.action, "VERIFY_UPPER_POLICY_PERMISSION")
        self.assertTrue(strat_policy.requires_human_approval)

        c_test = FailureClassifier.classify("AssertionError: 404 != 200")
        strat_test = DeterministicRepairStrategy.recommend(c_test)
        self.assertEqual(strat_test.action, "COUNTEREXAMPLE_DRIVEN_TEST_FIX")

    def test_oscillation_detector(self) -> None:
        from elmos_pi_harness.repair import OscillationDetector

        detector = OscillationDetector()
        c_a = FailureClassifier.classify("AssertionError: count is 1, expected 2")
        c_b = FailureClassifier.classify("TypeError: cannot add str to int")

        is_cycle_1, _ = detector.record_and_check(c_a)
        self.assertFalse(is_cycle_1)

        is_cycle_2, _ = detector.record_and_check(c_b)
        self.assertFalse(is_cycle_2)

        # Now repeat c_a -> oscillation cycle A -> B -> A detected!
        is_cycle_3, reason = detector.record_and_check(c_a)
        self.assertTrue(is_cycle_3)
        self.assertIn("Oscillation detected", reason)

    def test_rollback_advisor_and_doom_loop(self) -> None:
        ctrl = SelfHealingController(max_attempts=5, initial_generation=1)
        err_a = "File 'a.py', line 1\nAssertionError: x == 1"
        err_b = "File 'b.py', line 2\nTypeError: y == 2"

        # 1. First failure
        ctrl.record_failure(err_a, "task")
        self.assertTrue(ctrl.can_repair)

        # 2. Second failure introduces a more severe error: SYNTAX_ERROR
        ctrl.record_failure("File 'c.py', line 3\nSyntaxError: unexpected EOF", "task")
        recommendation = ctrl.suggest_rollback()
        # Degradation from TEST_FAILURE (severity 2) to SYNTAX_ERROR (severity 3)
        self.assertTrue(recommendation.should_rollback)
        self.assertIn("Degradation detected", recommendation.reason)

        # 3. Trigger oscillation doom-loop by repeating first error
        ctrl.record_failure(err_a, "task")
        self.assertTrue(ctrl.cycle_detected)
        self.assertFalse(ctrl.can_repair)

        # 4. Export evidence bundle
        evidence = ctrl.export_repair_evidence("DOOM_LOOP_HALTED")
        self.assertEqual(evidence["final_status"], "DOOM_LOOP_HALTED")
        self.assertTrue(evidence["cycle_detected"])
        self.assertTrue(evidence["evidence_digest"].startswith("sha256:"))
        self.assertEqual(evidence["total_attempts"], 3)


if __name__ == "__main__":
    unittest.main()
