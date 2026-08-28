import unittest
from reference_kernel.elmos_ai_factory.contract_compatibility_v4 import *
class T(unittest.TestCase):
 def test_compatible(self): self.assertEqual(classify_change({'a'},{'a'}),'compatible')
 def test_conditional(self): self.assertEqual(classify_change({'a'},{'a','b'}),'conditional')
 def test_breaking(self): self.assertEqual(classify_change({'a','b'},{'a'}),'breaking')
 def test_critical_missing(self): self.assertEqual(negotiate({'a','b'},{'a'},{'b'})['decision'],'BLOCK')
 def test_mixed(self): self.assertTrue(mixed_version_safe(True,True,True))
