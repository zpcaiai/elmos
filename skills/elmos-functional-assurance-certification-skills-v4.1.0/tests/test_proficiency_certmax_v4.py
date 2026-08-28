import unittest
from reference_kernel.elmos_ai_factory.proficiency import *
class T(unittest.TestCase):
 def test_z(self): self.assertEqual(z_score(12,10,1),2)
 def test_perf(self): self.assertEqual(performance(3.1),"UNSATISFACTORY")
