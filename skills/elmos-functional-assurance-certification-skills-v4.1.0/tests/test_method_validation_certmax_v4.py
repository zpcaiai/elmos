import unittest
from reference_kernel.elmos_ai_factory.method_validation import *
class T(unittest.TestCase):
 def test_cv(self): self.assertGreater(coefficient_of_variation([9,10,11]),0)
 def test_auth(self): self.assertTrue(method_authorized({"cv":.05},{"cv":.1}))
