import unittest
from reference_kernel.elmos_ai_factory.proof_replay import *
class T(unittest.TestCase):
 def test_digest(self): self.assertEqual(len(proof_digest("c","p",[])),64)
 def test_replay(self):
  x=proof_digest("c","p",[]); self.assertTrue(replay_matches(x,x))
