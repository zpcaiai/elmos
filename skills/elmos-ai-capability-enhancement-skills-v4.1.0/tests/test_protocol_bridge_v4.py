import unittest
from reference_kernel.elmos_ai_factory.protocol_bridge_v4 import *
class T(unittest.TestCase):
 def test_bridge(self): self.assertTrue(bridge_allowed(True,True,True,True))
 def test_bridge_loss(self): self.assertFalse(bridge_allowed(True,False,True,True))
 def test_read_hint(self): self.assertTrue(tool_hints_consistent(True,False,False,'read'))
 def test_delete_hint(self): self.assertTrue(tool_hints_consistent(False,True,False,'delete'))
 def test_extensions(self): self.assertTrue(extension_negotiated({'tasks'},{'tasks','apps'}))
