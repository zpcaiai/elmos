import unittest
from reference_kernel.elmos_ai_factory.record_replay_v4 import *
class T(unittest.TestCase):
 def test_normalize(self): self.assertEqual(normalize({'b':2,'a':1,'timestamp':3}),'{"a":1,"b":2}')
 def test_safe(self): self.assertTrue(replay_safe('suppressed',True))
 def test_unsafe(self): self.assertFalse(replay_safe('live',True))
 def test_trace(self): self.assertTrue(traces_equivalent([{'a':1}],[{'a':1}]))
 def test_retention(self): self.assertTrue(retention_allowed(True,30,10))
