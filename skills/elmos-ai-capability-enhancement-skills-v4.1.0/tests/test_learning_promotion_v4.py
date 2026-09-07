import unittest
from reference_kernel.elmos_ai_factory.learning_promotion_v4 import *
class T(unittest.TestCase):
 def test_promotion(self): self.assertTrue(promotion_allowed(True,True,True,True,False))
 def test_block(self): self.assertFalse(promotion_allowed(True,True,False,True,False))
 def test_arena(self): self.assertEqual(arena_winner([{'name':'a','quality':.8,'cost':1,'budget':2,'safety':True}]),'a')
 def test_arena_none(self):
  with self.assertRaises(LookupError): arena_winner([{'name':'a','quality':1,'cost':1,'budget':2,'safety':False}])
 def test_self_gate(self): self.assertFalse(self_gate_change_allowed('learner'))
