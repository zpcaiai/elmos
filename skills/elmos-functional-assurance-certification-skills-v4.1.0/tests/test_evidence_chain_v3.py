import unittest
from reference_kernel.elmos_ai_factory.evidence_chain import *
class T(unittest.TestCase):
 def test_append_verify(self):
  c=[];append_entry(c,"a","p");append_entry(c,"b","p");self.assertTrue(verify_chain(c))
 def test_tamper(self):
  c=[];append_entry(c,"a","p");c[0]["artifactHash"]="x";self.assertFalse(verify_chain(c))
 def test_empty_merkle(self):self.assertEqual(len(merkle_root([])),64)
 def test_one_merkle(self):self.assertEqual(merkle_root(["a"]),"a")
 def test_two_merkle(self):self.assertEqual(len(merkle_root(["a","b"])),64)
