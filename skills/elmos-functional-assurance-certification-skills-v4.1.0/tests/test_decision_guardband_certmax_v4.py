import unittest
from reference_kernel.elmos_ai_factory.decision_guardband import *
class T(unittest.TestCase):
 def test_pass(self): self.assertEqual(conformity_decision(8,10,1),"PASS")
 def test_indeterminate(self): self.assertEqual(conformity_decision(9.5,10,1),"INDETERMINATE")
