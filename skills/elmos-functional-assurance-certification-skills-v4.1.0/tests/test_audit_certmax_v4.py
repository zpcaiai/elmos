import unittest
from reference_kernel.elmos_ai_factory.audit import *
class T(unittest.TestCase):
 def test_sample(self): self.assertEqual(risk_weighted_sample([{"id":1,"risk":1},{"id":2,"risk":3}],1)[0]["id"],2)
 def test_sufficient(self): self.assertTrue(evidence_sufficient({"a"},{"a","b"}))
