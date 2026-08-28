import unittest
from reference_kernel.elmos_ai_factory.measurement_uncertainty import *
class T(unittest.TestCase):
 def test_combine(self): self.assertAlmostEqual(combined_standard_uncertainty([3,4]),5)
 def test_expand(self): self.assertEqual(expanded_uncertainty(2,2),4)
