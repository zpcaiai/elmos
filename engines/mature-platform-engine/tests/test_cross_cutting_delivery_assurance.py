"""Integration tests for cross-cutting delivery assurance scenarios (U024-U030)."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.finops_economics_engine import FinOpsEconomicsEngine
from elmos_mature_platform.kms_service import EnterpriseKmsService
from elmos_mature_platform.oidc_service import EnterpriseOidcProvider
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
from elmos_mature_platform.scenarios.cross_cutting_delivery_assurance import (
    execute_cross_cutting_delivery_assurance,
)


class TestDeliveryAssuranceBase(unittest.TestCase):
    def setUp(self) -> None:
        self.kms = EnterpriseKmsService()
        self.oidc = EnterpriseOidcProvider()
        self.finops = FinOpsEconomicsEngine()
        self.slo = EnterpriseSloCollector()
        self.trace_log: list[str] = []

    def _trace(self, msg: str) -> None:
        self.trace_log.append(msg)

    def _run(self, skill_code: str, category: str, case_id: str = "T-001") -> tuple[list, dict]:
        meta = {"case_id": case_id, "category": category, "skill_code": skill_code}
        return execute_cross_cutting_delivery_assurance(
            meta, self.kms, self.oidc, self.finops, self.slo, self._trace
        )

    def _assert_all_passed(self, assertions: list) -> None:
        self.assertTrue(len(assertions) > 0, "No assertions returned")
        for a in assertions:
            self.assertTrue(a.passed, f"Assertion '{a.name}' failed: {a.details}")


class TestU024FinOpsBilling(TestDeliveryAssuranceBase):
    """U024: tst-metering-billing-margin-reconciliation"""

    def test_success_billing_pipeline(self):
        """U024 success: tests finops pipeline"""
        assertions, metrics = self._run("U024", "success")
        self._assert_all_passed(assertions)
        self.assertIn("invoice_total_usd", metrics)
        self.assertIn("gross_margin_pct", metrics)

    def test_boundary_zero_usage(self):
        """U024 boundary: generates zero-usage invoice"""
        assertions, _ = self._run("U024", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_phantom_charge(self):
        assertions, _ = self._run("U024", "negative")
        self._assert_all_passed(assertions)

    def test_security_tenant_isolation(self):
        assertions, _ = self._run("U024", "security")
        self._assert_all_passed(assertions)


class TestU025EvidenceReview(TestDeliveryAssuranceBase):
    """U025: tst-customer-evidence-independent-review"""

    def test_success_independent_review(self):
        assertions, metrics = self._run("U025", "success")
        self._assert_all_passed(assertions)
        self.assertIn("independent_signoffs", metrics)

    def test_boundary_large_dossier(self):
        assertions, _ = self._run("U025", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_self_signed(self):
        assertions, _ = self._run("U025", "negative")
        self._assert_all_passed(assertions)

    def test_security_separation_of_authority(self):
        assertions, _ = self._run("U025", "security")
        self._assert_all_passed(assertions)


class TestU026CrossBatchMaturity(TestDeliveryAssuranceBase):
    """U026: tst-cross-batch-maturity-integration"""

    def test_success_end_to_end(self):
        assertions, metrics = self._run("U026", "success")
        self._assert_all_passed(assertions)
        self.assertIn("batches_integrated", metrics)

    def test_boundary_peak_load(self):
        assertions, _ = self._run("U026", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_contract_violation(self):
        assertions, _ = self._run("U026", "negative")
        self._assert_all_passed(assertions)

    def test_security_capability_leases(self):
        assertions, _ = self._run("U026", "security")
        self._assert_all_passed(assertions)


class TestU027PrivacyResidency(TestDeliveryAssuranceBase):
    """U027: tst-privacy-residency-retention-deletion"""

    def test_success_crypto_shredding(self):
        assertions, metrics = self._run("U027", "success")
        self._assert_all_passed(assertions)
        self.assertIn("crypto_shred_time_ms", metrics)

    def test_boundary_batch_capacity(self):
        assertions, _ = self._run("U027", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_cross_border(self):
        assertions, _ = self._run("U027", "negative")
        self._assert_all_passed(assertions)

    def test_security_legal_hold(self):
        assertions, _ = self._run("U027", "security")
        self._assert_all_passed(assertions)

    def test_crypto_shred_raises_permission_error(self):
        """Explicitly verify that decryption raises PermissionError after shredding."""
        key_id = "test-shred-key"
        self.kms.create_key(key_id)
        encrypted = self.kms.envelope_encrypt(key_id, b"secret data", "tenant-test", "patient-1")
        
        # Verify it can be decrypted before shredding
        decrypted = self.kms.envelope_decrypt(encrypted, "tenant-test", "patient-1")
        self.assertEqual(decrypted, b"secret data")
        
        # Shred the key
        self.kms.crypto_shred_key(key_id)
        
        # Verify PermissionError
        with self.assertRaises(PermissionError):
            self.kms.envelope_decrypt(encrypted, "tenant-test", "patient-1")


class TestU028PerformanceSLO(TestDeliveryAssuranceBase):
    """U028: tst-performance-capacity-cost-regression"""

    def test_success_slo_pipeline(self):
        assertions, metrics = self._run("U028", "success")
        self._assert_all_passed(assertions)
        self.assertIn("p95_latency_regression", metrics)

    def test_boundary_exact_threshold(self):
        assertions, _ = self._run("U028", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_regression_gate_failure(self):
        # Triggers performance regression gate failure
        assertions, _ = self._run("U028", "negative")
        # In the negative case, the gate failure means passed=False for the assertion
        self.assertGreater(len(assertions), 0)
        # We expect the assertion "Performance Regression Gate Failure" to be passed=False,
        # wait, the code says:
        # ScenarioAssertion("Performance Regression Gate Failure", not ok_fail, "15% regression correctly failed gate")
        # Let's check the code for U028 negative.
        # ok_fail will be False, so not ok_fail is True. Thus the assertion *passes*.
        self._assert_all_passed(assertions)

    def test_security_telemetry_redaction(self):
        assertions, _ = self._run("U028", "security")
        self._assert_all_passed(assertions)


class TestU029EvidenceReplay(TestDeliveryAssuranceBase):
    """U029: tst-evidence-replay-certification-anti-forgery"""

    def test_success_replay(self):
        assertions, metrics = self._run("U029", "success")
        self._assert_all_passed(assertions)
        self.assertIn("replay_pass_rate", metrics)

    def test_boundary_timeout(self):
        assertions, _ = self._run("U029", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_zero_tolerance(self):
        assertions, _ = self._run("U029", "negative")
        self._assert_all_passed(assertions)

    def test_security_key_protection(self):
        assertions, _ = self._run("U029", "security")
        self._assert_all_passed(assertions)


class TestU030StrictReleaseGate(TestDeliveryAssuranceBase):
    """U030: tst-b38-45-final-strict-release-gate"""

    def test_success_certification(self):
        assertions, metrics = self._run("U030", "success")
        self._assert_all_passed(assertions)
        self.assertIn("final_decision_certified", metrics)

    def test_boundary_zero_blockers(self):
        assertions, _ = self._run("U030", "boundary")
        self._assert_all_passed(assertions)

    def test_negative_failed_status(self):
        assertions, _ = self._run("U030", "negative")
        self._assert_all_passed(assertions)

    def test_security_signed_artifact(self):
        assertions, _ = self._run("U030", "security")
        self._assert_all_passed(assertions)


if __name__ == "__main__":
    unittest.main()
