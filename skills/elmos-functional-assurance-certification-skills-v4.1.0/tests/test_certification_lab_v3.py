import unittest
from reference_kernel.elmos_ai_factory.certification_lab import *
class T(unittest.TestCase):
 def req(self):return {"producerIdentity":"gen","certifierIdentity":"cert","exactRevisionSet":"r","evidenceChainValid":True,"gates":{g:"PASS" for g in REQUIRED_GATES},"criticalUnknown":0,"unsettledSideEffects":0,"scope":"s"}
 def test_certify(self):self.assertEqual(evaluate(self.req())["decision"],"CERTIFIED")
 def test_independence(self):
  r=self.req();r["certifierIdentity"]="gen";self.assertEqual(evaluate(r)["reason"],"independence")
 def test_gate(self):
  r=self.req();r["gates"]["E5"]="FAIL";self.assertEqual(evaluate(r)["decision"],"BLOCKED")
 def test_affected(self):self.assertEqual(affected_claims({"claimDependencies":{"a":["x"],"b":["y"]}},{"x"}),{"a"})
 def test_waiver(self):self.assertTrue(waiver_active({"status":"APPROVED","expiresAtEpoch":10,"owner":"o"},5))
