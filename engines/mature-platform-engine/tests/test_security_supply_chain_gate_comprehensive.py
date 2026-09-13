import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    SupplyChainCheckType,
    SupplyChainGateAssessment,
    SupplyChainGateCheck,
    SupplyChainGateVerdict,
)
from elmos_mature_platform.security_supply_chain_gate_engine import SecuritySupplyChainGateEngine


class TestSecuritySupplyChainGateComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SecuritySupplyChainGateEngine()

    def test_initiate_assessment(self):
        aid = self.engine.initiate_assessment("rel-1.0.0", "sha256:abcd1234efgh5678")
        self.assertTrue(aid.startswith("scg-"))
        asm = self.engine.get_assessment(aid)
        self.assertIsNotNone(asm)
        self.assertEqual(asm.release_id, "rel-1.0.0")
        self.assertEqual(asm.verdict, SupplyChainGateVerdict.REJECTED)

    def test_initiate_assessment_missing_fields(self):
        with self.assertRaises(ValueError):
            self.engine.initiate_assessment("", "sha256:123")
        with self.assertRaises(ValueError):
            self.engine.initiate_assessment("rel-1.0", "")

    def test_add_and_record_check(self):
        aid = self.engine.initiate_assessment("rel-1.0.1", "sha256:1111")
        chk = SupplyChainGateCheck(
            check_id="chk-slsa",
            check_type=SupplyChainCheckType.SLSA_LEVEL,
            name="SLSA Level 3 Provenance Verified",
            blocking=True,
        )
        self.engine.add_check(aid, chk)
        res = self.engine.record_check_result(aid, "chk-slsa", passed=True, details="Cosign attestation validated")
        self.assertTrue(res.passed)
        self.assertEqual(res.details, "Cosign attestation validated")

    def test_evaluate_gate_all_passed(self):
        aid = self.engine.initiate_assessment("rel-green", "sha256:green")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SLSA_LEVEL, name="SLSA", blocking=True)
        c2 = SupplyChainGateCheck(check_id="c2", check_type=SupplyChainCheckType.SBOM_VALIDITY, name="SBOM", blocking=True)
        c3 = SupplyChainGateCheck(check_id="c3", check_type=SupplyChainCheckType.SECRET_FREE, name="Secrets", blocking=True)

        self.engine.add_check(aid, c1)
        self.engine.add_check(aid, c2)
        self.engine.add_check(aid, c3)

        self.engine.record_check_result(aid, "c1", passed=True)
        self.engine.record_check_result(aid, "c2", passed=True)
        self.engine.record_check_result(aid, "c3", passed=True)

        evaluated = self.engine.evaluate_gate(aid, evaluator="gate-verifier")
        self.assertEqual(evaluated.verdict, SupplyChainGateVerdict.APPROVED)

    def test_evaluate_gate_blocking_failure(self):
        aid = self.engine.initiate_assessment("rel-blocked", "sha256:bad")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SECRET_FREE, name="Secrets", blocking=True)
        self.engine.add_check(aid, c1)
        self.engine.record_check_result(aid, "c1", passed=False, details="Detected exposed AWS key")

        evaluated = self.engine.evaluate_gate(aid)
        self.assertEqual(evaluated.verdict, SupplyChainGateVerdict.REJECTED)
        failed_blocking = self.engine.get_failed_blocking_checks(aid)
        self.assertEqual(len(failed_blocking), 1)

    def test_evaluate_gate_non_blocking_conditional_waiver(self):
        aid = self.engine.initiate_assessment("rel-advisory", "sha256:adv")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SLSA_LEVEL, name="SLSA", blocking=True)
        c2 = SupplyChainGateCheck(check_id="c2", check_type=SupplyChainCheckType.VULNERABILITY_THRESHOLD, name="Low CVEs", blocking=False)

        self.engine.add_check(aid, c1)
        self.engine.add_check(aid, c2)

        self.engine.record_check_result(aid, "c1", passed=True)
        self.engine.record_check_result(aid, "c2", passed=False, details="2 low severity CVEs pending patch")

        evaluated = self.engine.evaluate_gate(aid)
        self.assertEqual(evaluated.verdict, SupplyChainGateVerdict.CONDITIONAL_WAIVER)

    def test_emergency_waiver_prohibited_for_slsa(self):
        aid = self.engine.initiate_assessment("rel-no-slsa", "sha256:noslsa")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SLSA_LEVEL, name="SLSA", blocking=True)
        self.engine.add_check(aid, c1)
        self.engine.record_check_result(aid, "c1", passed=False)
        self.engine.evaluate_gate(aid)

        with self.assertRaises(PermissionError):
            self.engine.grant_emergency_waiver(aid, justification="Urgent patch", approver="VP Eng")

    def test_emergency_waiver_allowed_for_non_slsa(self):
        aid = self.engine.initiate_assessment("rel-vuln-waiver", "sha256:waiver")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SIGNATURE_VERIFIED, name="Sig", blocking=True)
        self.engine.add_check(aid, c1)
        self.engine.record_check_result(aid, "c1", passed=False)
        self.engine.evaluate_gate(aid)

        waived = self.engine.grant_emergency_waiver(aid, justification="Signing key expired, verified via out-of-band hash", approver="CISO")
        self.assertEqual(waived.verdict, SupplyChainGateVerdict.CONDITIONAL_WAIVER)
        self.assertIn("CISO", waived.waiver_justification)

    def test_get_supply_chain_gate_report(self):
        aid1 = self.engine.initiate_assessment("rel-1", "sha256:1")
        c1 = SupplyChainGateCheck(check_id="c1", check_type=SupplyChainCheckType.SLSA_LEVEL, name="SLSA", blocking=True)
        self.engine.add_check(aid1, c1)
        self.engine.record_check_result(aid1, "c1", passed=True)
        self.engine.evaluate_gate(aid1)

        aid2 = self.engine.initiate_assessment("rel-2", "sha256:2")
        c2 = SupplyChainGateCheck(check_id="c2", check_type=SupplyChainCheckType.SECRET_FREE, name="Secrets", blocking=True)
        self.engine.add_check(aid2, c2)
        self.engine.record_check_result(aid2, "c2", passed=False)
        self.engine.evaluate_gate(aid2)

        rep = self.engine.get_supply_chain_gate_report()
        self.assertEqual(rep["total_assessments"], 2)
        self.assertEqual(rep["approved_count"], 1)
        self.assertEqual(rep["rejected_count"], 1)
        self.assertEqual(rep["pass_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
