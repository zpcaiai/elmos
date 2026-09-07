import unittest
from reference_kernel.elmos_ai_factory.calibration import *
class T(unittest.TestCase):
 def test_brier(self): self.assertAlmostEqual(brier_score([1,0],[1,0]),0)
 def test_ece(self): self.assertAlmostEqual(calibration_error([(.8,.6,10)]),.2)
