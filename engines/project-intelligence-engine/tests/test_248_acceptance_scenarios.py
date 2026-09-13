import unittest
from elmos_project_intelligence.task_execution.scenario_verifier import (
    AcceptanceScenarioVerifier,
)
from elmos_project_intelligence.task_execution.task_resilience import ResilientTaskExecutor

class AcceptanceScenariosTests(unittest.TestCase):
    def setUp(self):
        self.verifier = AcceptanceScenarioVerifier()

    def test_all_248_scenarios_loaded(self):
        self.assertEqual(len(self.verifier.scenarios), 248)
        self.assertEqual(len(self.verifier.skill_scenarios), 50)

    def test_scenario_verification_samples(self):
        sample_ids = [
            'AC-00-01',
            'AC-00-02',
            'AC-00-03',
            'AC-10-02',
            'AC-25-01',
            'AC-49-05',
        ]
        for sid in sample_ids:
            verdict = self.verifier.verify_scenario(sid)
            self.assertEqual(verdict.status, 'PASSED')
            self.assertTrue(verdict.given_verified)
            self.assertTrue(verdict.when_executed)
            self.assertTrue(verdict.then_satisfied)
            self.assertGreater(len(verdict.evidence_collected), 0)

    def test_verify_batch_00(self):
        verdicts = self.verifier.verify_batch('BATCH-00-product-and-reference-architecture')
        self.assertGreater(len(verdicts), 0)
        for v in verdicts:
            self.assertEqual(v.status, 'PASSED')

    def test_verify_all_248_scenarios(self):
        all_verdicts = self.verifier.verify_all_scenarios()
        self.assertEqual(len(all_verdicts), 248)
        for sid, v in all_verdicts.items():
            self.assertEqual(v.status, 'PASSED')

    def test_checkpoint_resume_and_idempotency_ac_00_03(self):
        executor = ResilientTaskExecutor()
        call_count = 0
        def _operation():
            nonlocal call_count
            call_count += 1
            return {'result': 'success', 'data_count': 100}

        r1 = executor.execute_idempotent('task-001', _operation)
        self.assertEqual(r1['status'], 'EXECUTED_FRESH')
        self.assertEqual(call_count, 1)

        # Re-run after interruption
        r2 = executor.execute_idempotent('task-001', _operation)
        self.assertEqual(r2['status'], 'REPLAYED_FROM_CACHE')
        self.assertFalse(r2['side_effects_repeated'])
        self.assertEqual(call_count, 1)  # No second invocation
