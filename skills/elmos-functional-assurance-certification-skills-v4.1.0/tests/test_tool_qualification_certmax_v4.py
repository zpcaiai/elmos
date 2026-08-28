import unittest
from reference_kernel.elmos_ai_factory.tool_qualification import *
class T(unittest.TestCase):
 def test_level(self): self.assertEqual(qualification_level(True,False,False),"TQL-1")
 def test_credit(self): self.assertTrue(credit_allowed("TQL-2",True,True))
