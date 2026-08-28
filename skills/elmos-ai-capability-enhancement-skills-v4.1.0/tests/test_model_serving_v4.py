import unittest
from reference_kernel.elmos_ai_factory.model_serving_v4 import *
class T(unittest.TestCase):
 def test_quant(self): self.assertTrue(quantization_acceptable(.9,.895,0,.01))
 def test_quant_safety(self): self.assertFalse(quantization_acceptable(.9,.9,1,.01))
 def test_promote(self): self.assertTrue(can_promote(True,True,True,True,True))
 def test_route(self): self.assertEqual(choose_route([{'name':'a','capabilities':['x'],'cost':1,'p95':2,'available':True}],{'x'},2),'a')
 def test_drift(self): self.assertTrue(drift_invalidates('a','b'))
