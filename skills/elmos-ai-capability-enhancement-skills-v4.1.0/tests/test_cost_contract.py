import unittest
from decimal import Decimal
from reference_kernel.elmos_ai_factory.cost_contract import Usage,Rates,calculate_cost,budget_decision
class CostTests(unittest.TestCase):
 def rates(self):return Rates(Decimal('1'),Decimal('2'),Decimal('.1'),Decimal('.01'),Decimal('.02'))
 def test_cost(self):self.assertEqual(Decimal('1.500000'),calculate_cost(Usage(100000,200000,Decimal('10')),self.rates()))
 def test_budget(self):self.assertEqual('BLOCKED',budget_decision(Decimal('11'),Decimal('10')))
 def test_negative_rejected(self):
  with self.assertRaises(ValueError):calculate_cost(Usage(-1),self.rates())
