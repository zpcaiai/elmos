from __future__ import annotations

import unittest

from scripts.language_packs_b81_95.engine import DeterministicEngine
from scripts.language_packs_b81_95.errors import BudgetExceeded


class DeterminismAndWorkerInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DeterministicEngine(max_steps=100)

    def test_replay_is_bit_identical(self) -> None:
        payload = {
            'sources': [
                {'path': 'test.src', 'content': 'PROGRAM main\nBEGIN\nEND'}
            ]
        }
        res1 = self.engine.execute_skill('PG223', 'discovery-inventory', payload)
        res2 = self.engine.execute_skill('PG223', 'discovery-inventory', payload)

        self.assertEqual(res1.output_digest, res2.output_digest)
        self.assertTrue(res2.replayed)

    def test_verify_replay_helper(self) -> None:
        payload = {'source_code': 'VAR a = 1', 'language': 'Lua'}
        self.assertTrue(self.engine.verify_replay('PG392', 'parser-semantic-model', payload))

    def test_worker_invariance(self) -> None:
        units = [
            ('PG223', 'discovery-inventory', {'sources': [{'path': f'f{i}.src', 'content': f'val={i}'}]})
            for i in range(20)
        ]
        self.assertTrue(self.engine.verify_worker_invariance(units))

    def test_step_budget_enforcement(self) -> None:
        small_engine = DeterministicEngine(max_steps=3)
        for i in range(3):
            small_engine.execute_skill(f'PG{223+i}', 'discovery-inventory', {'sources': []})
        with self.assertRaises(BudgetExceeded):
            small_engine.execute_skill('PG226', 'discovery-inventory', {'sources': []})


if __name__ == '__main__':
    unittest.main()
