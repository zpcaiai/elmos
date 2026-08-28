import unittest
from reference_kernel.elmos_ai_factory.explainability import *
class T(unittest.TestCase):
 def test_overlap(self): self.assertGreater(top_k_overlap([1,2],[1,3],2),0)
 def test_fidelity(self): self.assertEqual(fidelity([1,2],[1,2]),1)
