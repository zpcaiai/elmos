import unittest
from reference_kernel.elmos_ai_factory.route_optimizer_v4 import *
class T(unittest.TestCase):
 def test_mandatory(self): self.assertEqual(select_tests([{'id':'a','cost':1,'mandatory':True}],1),['a'])
 def test_over(self):
  with self.assertRaises(RuntimeError): select_tests([{'id':'a','cost':2,'mandatory':True}],1)
 def test_optional(self): self.assertIn('b',select_tests([{'id':'a','cost':1,'mandatory':True},{'id':'b','cost':1,'risk':2}],2))
 def test_route(self): self.assertEqual(choose_route([{'name':'r','coverage':1,'reversibility':1,'risk':1,'cost':1,'native':True,'rollback':True}]),'r')
 def test_no_route(self):
  with self.assertRaises(LookupError): choose_route([])
