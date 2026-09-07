import unittest
from reference_kernel.elmos_ai_factory.validation_dag import *
class T(unittest.TestCase):
 def test_order(self):self.assertEqual(topological_order(["a","b"],[("a","b")]),["a","b"])
 def test_cycle(self):
  with self.assertRaises(ValueError):topological_order(["a","b"],[("a","b"),("b","a")])
 def test_unknown(self):
  with self.assertRaises(KeyError):topological_order(["a"],[("a","b")])
 def test_select(self):self.assertEqual(select_cases([{"id":"x","risk":"critical"}],set()),["x"])
 def test_critical_path(self):self.assertEqual(critical_path(["a","b"],{"a":1,"b":2},[("a","b")]),(3,["a","b"]))
