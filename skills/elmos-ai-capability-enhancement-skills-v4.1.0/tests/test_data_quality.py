import unittest
from reference_kernel.elmos_ai_factory.data_quality import QualityResult,quality_gate
class DataQualityTests(unittest.TestCase):
 def test_good(self):self.assertEqual('PASS',quality_gate(QualityResult(1,0,10,.01))[0])
 def test_drift_blocks(self):self.assertIn('distribution-drift',quality_gate(QualityResult(1,0,10,.5))[1])
 def test_stale_blocks(self):self.assertEqual('BLOCKED',quality_gate(QualityResult(1,0,9999,.01))[0])
