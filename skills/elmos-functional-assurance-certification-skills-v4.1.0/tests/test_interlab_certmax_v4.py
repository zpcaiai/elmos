import unittest
from reference_kernel.elmos_ai_factory.interlab import *
class T(unittest.TestCase):
 def test_location(self): self.assertEqual(robust_location([1,100,2]),2)
 def test_sd(self): self.assertGreater(reproducibility_sd([1,2,3]),0)
