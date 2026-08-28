import unittest
from reference_kernel.elmos_ai_factory.incident import IncidentController
class IncidentTests(unittest.TestCase):
 def test_stale_control_rejected(self):self.assertEqual('STALE_REJECTED',IncidentController('i').apply(generation=0,scope='tenant',target='t'))
 def test_monotonic_disable(self):
  i=IncidentController('i');i.apply(generation=1,scope='tool',target='x');self.assertEqual('MONOTONIC_REJECTED',i.apply(generation=1,scope='tool',target='x',state='enabled'))
 def test_restart_requires_all_gates(self):
  i=IncidentController('i');self.assertEqual('BLOCKED',i.safe_restart());i.evidence_frozen=i.side_effects_settled=i.root_cause_closed=True;self.assertEqual('ALLOW',i.safe_restart())
