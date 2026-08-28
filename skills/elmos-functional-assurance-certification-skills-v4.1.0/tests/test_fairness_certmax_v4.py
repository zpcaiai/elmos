import unittest
from reference_kernel.elmos_ai_factory.fairness import *
class T(unittest.TestCase):
 def test_diff(self): self.assertAlmostEqual(demographic_parity_difference(5,10,4,10),.1)
 def test_ratio(self): self.assertAlmostEqual(four_fifths_ratio(8,10,4,10),.5)
