import unittest
from reference_kernel.elmos_ai_factory.human_factors import *
class T(unittest.TestCase):
 def test_rate(self): self.assertEqual(overreliance_rate(2,10),.2)
 def test_gate(self): self.assertTrue(safe_reliance_gate(.1,.2,True))
