import unittest
from reference_kernel.elmos_ai_factory.certifier import ProofResult, CertificationInput, certify

def proof(status="TESTED", criticality="critical", rev="rev-1", obligation="po-1"):
    return ProofResult(obligation,criticality,status,"e"*64,"sha256:"+"v"*64,rev)

def valid_input(**overrides):
    base=dict(
      revision_set_id="rev-1",proof_results=[proof()],
      gates={f"E{i}":"PASS" for i in range(6)},p05="PASS",
      certifier_independent=True,evidence_bundle_sealed=True,
      evidence_revision_set_id="rev-1",side_effects_settled=True,production=True)
    base.update(overrides)
    return CertificationInput(**base)

class CertifierTests(unittest.TestCase):
    def test_certifies_exact_complete_evidence(self):
        decision=certify(valid_input())
        self.assertEqual("CERTIFIED",decision.decision)
        self.assertEqual("rev-1",decision.certified_revision_set_id)

    def test_critical_unknown_blocks(self):
        decision=certify(valid_input(proof_results=[proof("UNKNOWN")]))
        self.assertEqual("BLOCKED",decision.decision)
        self.assertTrue(any("non-certifiable" in r for r in decision.reasons))

    def test_revision_mismatch_blocks(self):
        decision=certify(valid_input(evidence_revision_set_id="rev-old"))
        self.assertEqual("BLOCKED",decision.decision)

    def test_non_independent_certifier_blocks(self):
        decision=certify(valid_input(certifier_independent=False))
        self.assertEqual("BLOCKED",decision.decision)

    def test_e5_or_p05_failure_blocks(self):
        gates={f"E{i}":"PASS" for i in range(6)}
        gates["E5"]="BLOCKED"
        decision=certify(valid_input(gates=gates,p05="FAIL"))
        self.assertEqual("BLOCKED",decision.decision)
        self.assertIn("E5 is not PASS",decision.reasons)
        self.assertIn("P05 is not PASS for production",decision.reasons)
