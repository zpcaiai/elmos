import unittest
from reference_kernel.elmos_ai_factory.compliance import Control,profile_decision
class ComplianceTests(unittest.TestCase):
 def test_complete(self):self.assertEqual('READY_FOR_INDEPENDENT_GATE',profile_decision([Control('c',True,'impl',('ev',))],legal_review_approved=False)[0])
 def test_missing_evidence_blocks(self):self.assertEqual('BLOCKED',profile_decision([Control('c',True,'impl',())],legal_review_approved=True)[0])
 def test_legal_review_blocks(self):self.assertIn('legal:c',profile_decision([Control('c',True,'impl',('ev',),True)],legal_review_approved=False)[1])
