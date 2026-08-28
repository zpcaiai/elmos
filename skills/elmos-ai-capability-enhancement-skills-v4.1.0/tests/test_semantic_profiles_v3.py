import unittest
from reference_kernel.elmos_ai_factory.semantic_profiles import *
class T(unittest.TestCase):
 def test_equal(self):self.assertEqual(compare_profiles({"numeric":"wrap"},{"numeric":"wrap"},["numeric"]),[])
 def test_gap(self):self.assertEqual(compare_profiles({"numeric":"wrap"},{"numeric":"checked"},["numeric"])[0]["severity"],"critical")
 def test_preserved(self):self.assertEqual(classify_resolution({"dimension":"numeric"},{"numeric"}),"PRESERVED")
 def test_emulated(self):self.assertEqual(classify_resolution({"dimension":"numeric"},{"emulate:numeric"}),"EMULATED")
 def test_critical_open(self):self.assertEqual(critical_open([{"severity":"critical","status":"OPEN"},{"severity":"high","status":"OPEN"}]),1)
