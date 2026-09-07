import unittest
from reference_kernel.elmos_ai_factory.tcb import *
class T(unittest.TestCase):
 def test_closed(self): self.assertTrue(tcb_closed([{"pinned":1,"verified":1,"owner":"x"}]))
 def test_score(self): self.assertEqual(attack_surface_score([{"exposure":2,"criticality":3}]),6)
