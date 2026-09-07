import unittest
from reference_kernel.elmos_ai_factory.tenant_memory import MemoryRecord,authorize_memory,isolation_probe
class TenantMemoryTests(unittest.TestCase):
 def test_owner_allowed(self):self.assertEqual('ALLOW',authorize_memory(MemoryRecord('r','t','user','u'),tenant_id='t',principal_id='u',allowed_scopes=frozenset({'user'})))
 def test_cross_tenant_denied(self):self.assertEqual('DENY_TENANT',authorize_memory(MemoryRecord('r','x','user','u'),tenant_id='t',principal_id='u',allowed_scopes=frozenset({'user'})))
 def test_probe_finds_leak(self):self.assertFalse(isolation_probe([MemoryRecord('r','x','user','u')],tenant_id='t')[0])
