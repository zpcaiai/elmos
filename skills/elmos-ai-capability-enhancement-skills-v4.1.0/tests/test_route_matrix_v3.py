import unittest
from reference_kernel.elmos_ai_factory.route_matrix import *
class T(unittest.TestCase):
 def routes(self):return [{"source":"py","target":"java","versions":["3.13","21"],"status":"certified","risk":1,"evidenceDependencies":["compiler","adapter"]}]
 def test_exact(self):self.assertEqual(select_route(self.routes(),"py","java",("3.13","21"))["status"],"certified")
 def test_no_exact(self):
  with self.assertRaises(LookupError):select_route(self.routes(),"py","java",("3.12","21"))
 def test_blocked(self):
  with self.assertRaises(PermissionError):select_route([{**self.routes()[0],"status":"blocked"}],"py","java",("3.13","21"))
 def test_invalidate(self):self.assertEqual(invalidate_route(self.routes()[0],{"compiler"}),{"compiler"})
 def test_overlay(self):self.assertTrue(pair_overlay_allowed({"preconditions":[1],"proofObligations":[1],"authority":"K3"}))
