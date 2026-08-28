import unittest
from reference_kernel.elmos_ai_factory.robustness import *
class T(unittest.TestCase):
 def test_worst(self): self.assertEqual(worst_case_accuracy([.9,.7,.8]),.7)
 def test_gate(self): self.assertTrue(robustness_gate(.9,.85,.1))
