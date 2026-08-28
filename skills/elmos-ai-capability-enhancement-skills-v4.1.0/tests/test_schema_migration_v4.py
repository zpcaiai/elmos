import unittest
from reference_kernel.elmos_ai_factory.schema_migration_v4 import *
class T(unittest.TestCase):
 def test_expand(self): self.assertTrue(expand_contract_allowed(True,True,True,0))
 def test_old_reader(self): self.assertFalse(expand_contract_allowed(True,True,True,1))
 def test_rollback(self): self.assertTrue(rollback_ready(True,True,True))
 def test_rollback_missing(self): self.assertFalse(rollback_ready(True,False,True))
 def test_online(self): self.assertTrue(online_change_safe(1,2,3,4))
