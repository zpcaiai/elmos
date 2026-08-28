import unittest
from reference_kernel.elmos_ai_factory.surveillance import *
class T(unittest.TestCase):
 def test_due(self): self.assertTrue(surveillance_due(10,.1,True,0))
 def test_suspend(self): self.assertEqual(certificate_action(True,True,False),"SUSPEND")
