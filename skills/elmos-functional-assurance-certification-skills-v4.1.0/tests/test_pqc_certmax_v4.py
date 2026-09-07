import unittest
from reference_kernel.elmos_ai_factory.pqc import *
class T(unittest.TestCase):
 def test_block(self): self.assertEqual(transition_status([{"algorithm":"RSA"}]),"BLOCKED")
 def test_hybrid(self): self.assertTrue(hybrid_required(True,False))
