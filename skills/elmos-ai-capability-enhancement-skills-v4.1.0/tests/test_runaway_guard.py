import unittest
from reference_kernel.elmos_ai_factory.runaway_guard import BudgetLimit,RunawayGuard
class RunawayTests(unittest.TestCase):
 def guard(self):return RunawayGuard(BudgetLimit(10,100,10,1000,60,3))
 def test_budget_termination(self):self.assertEqual('TERMINATE_BUDGET',self.guard().charge({'tokens':101}))
 def test_loop_termination(self):
  g=self.guard();[g.charge({'steps':1},'same') for _ in range(3)];self.assertEqual('TERMINATE_LOOP',g.charge({'steps':1},'same'))
 def test_counter_cannot_be_negative(self):
  with self.assertRaises(ValueError):self.guard().charge({'tokens':-1})
