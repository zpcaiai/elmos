import unittest
from reference_kernel.elmos_ai_factory.human_ux import ActionPreview,ux_gate
class HumanUxTests(unittest.TestCase):
 def preview(self,**kw):
  d=dict(action_digest='d',consequence='writes record',reversible=True,uncertainty='low',approval_required=True,cancel_available=True);d.update(kw);return ActionPreview(**d)
 def test_allow(self):self.assertEqual('ALLOW',ux_gate(self.preview(),shown_digest='d',consented=True)[0])
 def test_digest_mismatch(self):self.assertIn('digest-mismatch',ux_gate(self.preview(),shown_digest='x',consented=True)[1])
 def test_missing_consent(self):self.assertEqual('BLOCKED',ux_gate(self.preview(),shown_digest='d',consented=False)[0])
