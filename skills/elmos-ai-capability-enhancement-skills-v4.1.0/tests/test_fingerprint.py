import unittest
from reference_kernel.elmos_ai_factory.fingerprint import compare_fingerprints,recertification_decision
class FingerprintTests(unittest.TestCase):
 def test_no_drift_reuses(self):self.assertEqual('REUSE_EVIDENCE',recertification_decision(compare_fingerprints({'resolvedModel':'a'},{'resolvedModel':'a'})))
 def test_model_drift_recertifies(self):self.assertEqual('RECERTIFY',recertification_decision(compare_fingerprints({'resolvedModel':'a'},{'resolvedModel':'b'})))
 def test_noncritical_is_review(self):self.assertEqual('BOUNDED_REVIEW',recertification_decision(compare_fingerprints({'latency':1},{'latency':2})))
