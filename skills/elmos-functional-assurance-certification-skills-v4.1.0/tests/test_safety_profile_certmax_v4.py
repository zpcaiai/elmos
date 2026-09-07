import unittest
from reference_kernel.elmos_ai_factory.safety_profile import *
class T(unittest.TestCase):
 def test_risk(self): self.assertAlmostEqual(residual_risk(10,.1,.5),.5)
 def test_gate(self): self.assertTrue(safety_gate(.1,.2,True,True))
