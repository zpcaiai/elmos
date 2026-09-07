import unittest
from reference_kernel.elmos_ai_factory.statistical_gate import *
class T(unittest.TestCase):
 def test_percentile(self):self.assertEqual(percentile([1,2,3],.5),2)
 def test_empty(self):
  with self.assertRaises(ValueError):percentile([],.5)
 def test_ci(self):self.assertEqual(round(mean_ci95([1,2,3])[0],2),2)
 def test_insufficient(self):self.assertEqual(regression_gate([1],[1],.1)["decision"],"BLOCKED")
 def test_regression(self):self.assertEqual(regression_gate([1]*5,[2]*5,.1)["decision"],"FAIL")
