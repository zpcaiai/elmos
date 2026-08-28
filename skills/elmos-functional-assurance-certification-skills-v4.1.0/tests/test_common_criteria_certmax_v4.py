import unittest
from reference_kernel.elmos_ai_factory.common_criteria import *
class T(unittest.TestCase):
 def test_units(self): self.assertTrue(work_units_complete(["a"],{"a":"PASS"}))
 def test_vuln(self): self.assertFalse(vulnerability_gate([{"severity":"high","status":"open"}]))
