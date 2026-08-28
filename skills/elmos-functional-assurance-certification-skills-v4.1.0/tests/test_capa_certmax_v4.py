import unittest
from reference_kernel.elmos_ai_factory.capa import *
class T(unittest.TestCase):
 def test_root(self): self.assertTrue(root_cause_complete({"problem":"p","cause":"c","evidence":"e","systemic_scope":"s"}))
 def test_effective(self): self.assertTrue(effectiveness_pass(10,2,3))
