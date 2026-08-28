import unittest
from reference_kernel.elmos_ai_factory.recognition import *
class T(unittest.TestCase):
 def test_scope(self): self.assertTrue(scope_match({"a"},{"a","b"}))
 def test_decision(self): self.assertEqual(recognition_decision(True,True,True,True),"ACCEPTED")
