import unittest
from reference_kernel.elmos_ai_factory.certificate_profile import *
class T(unittest.TestCase):
 def test_digest(self): self.assertEqual(len(certificate_digest({"a":1})),64)
 def test_status(self): self.assertTrue(status_valid("ACTIVE",True))
