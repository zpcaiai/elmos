import unittest
from reference_kernel.elmos_ai_factory.rag_security import RetrievalCandidate,authorize_candidates,deletion_reconciled
class RagSecurityTests(unittest.TestCase):
 def test_acl_and_tenant(self):
  rows=[RetrievalCandidate('ok','t',frozenset({'u'}),False,.1,'s'),RetrievalCandidate('bad','other',frozenset({'u'}),False,.1,'s')];a,f=authorize_candidates(rows,tenant_id='t',principal='u');self.assertEqual(['ok'],[x.document_id for x in a]);self.assertIn('cross-tenant:bad',f)
 def test_poison_quarantined(self):
  _,f=authorize_candidates([RetrievalCandidate('p','t',frozenset({'u'}),False,.9,'s')],tenant_id='t',principal='u');self.assertIn('poison-quarantine:p',f)
 def test_delete_reconciliation(self):self.assertTrue(deletion_reconciled('x',{'vector':set(),'cache':{'y'}}));self.assertFalse(deletion_reconciled('x',{'vector':{'x'}}))
