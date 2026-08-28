import unittest
from reference_kernel.elmos_ai_factory.assurance_dossier import *
class T(unittest.TestCase):
 def evidence(self):return [{"id":"e1","supports":["q"],"createdAtEpoch":9,"status":"VALID","confidence":.9,"answer":{"value":1,"secret":"x"}}]
 def test_supported(self):self.assertEqual(build_answer("q",self.evidence(),5,10)["status"],"SUPPORTED")
 def test_redacted(self):self.assertNotIn("secret",build_answer("q",self.evidence(),5,10)["answer"])
 def test_stale(self):self.assertEqual(build_answer("q",self.evidence(),0,10)["status"],"UNKNOWN")
 def test_ready(self):self.assertTrue(dossier_ready({"a":{"status":"SUPPORTED"}},{"a"})["ready"])
 def test_missing(self):self.assertFalse(dossier_ready({}, {"a"})["ready"])
