import unittest
from reference_kernel.elmos_ai_factory.attestation import *
class T(unittest.TestCase):
 def test_pass(self): self.assertEqual(appraise({"nonce":"n","measurement":"m","signature_valid":1},{"measurement":"m"},"n"),"PASS")
 def test_admit(self): self.assertFalse(admission_allowed("REJECT",True))
