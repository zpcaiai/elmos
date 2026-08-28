import unittest
from reference_kernel.elmos_ai_factory.cache_consistency import CacheContext,semantic_key,cache_reuse_decision
class CacheConsistencyTests(unittest.TestCase):
 def ctx(self,**kw):
  d=dict(tenant_id='t',policy_digest='p',model_fingerprint='m',tool_digest='x',corpus_version='c',prompt_digest='q');d.update(kw);return CacheContext(**d)
 def test_stable_key(self):self.assertEqual(semantic_key(self.ctx(),'x'),semantic_key(self.ctx(),'x'))
 def test_tenant_change_miss(self):self.assertEqual('MISS',cache_reuse_decision(self.ctx(),self.ctx(tenant_id='u'),fresh=True)[0])
 def test_quarantine_miss(self):self.assertIn('quarantined',cache_reuse_decision(self.ctx(),self.ctx(),fresh=True,quarantined=True)[1])
