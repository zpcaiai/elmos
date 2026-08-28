import unittest
from reference_kernel.elmos_ai_factory.conformal import *
class T(unittest.TestCase):
 def test_coverage(self): self.assertEqual(empirical_coverage([1,1,0,1]),.75)
 def test_gate(self): self.assertTrue(coverage_gate(.89,.9,.02))
