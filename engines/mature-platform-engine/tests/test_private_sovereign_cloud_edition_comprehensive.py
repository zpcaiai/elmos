"""Comprehensive test suite for PrivateSovereignCloudEditionEngine (B38 - Skill 1327)."""

import unittest

from elmos_mature_platform.private_sovereign_cloud_edition_engine import (
    PrivateSovereignCloudEditionEngine,
)
from elmos_mature_platform.types import (
    AirgapEnclaveType,
    SovereignJurisdiction,
)


class TestPrivateSovereignCloudEditionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PrivateSovereignCloudEditionEngine()

    def test_register_strict_airgap_enclave(self):
        spec = self.engine.register_enclave(
            edition_id="ed-eu-sovereign",
            jurisdiction=SovereignJurisdiction.EU_GDPR,
            enclave_type=AirgapEnclaveType.HARDWARE_AIRGAP,
            allow_egress=False,
        )
        self.assertIsNotNone(spec)
        self.assertEqual(spec.jurisdiction, SovereignJurisdiction.EU_GDPR)
        self.assertFalse(spec.allow_egress)

        fetched = self.engine.get_enclave(spec.enclave_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.edition_id, "ed-eu-sovereign")

    def test_intercept_egress_traffic_blocked_when_egress_false(self):
        spec = self.engine.register_enclave(
            edition_id="ed-strict",
            jurisdiction=SovereignJurisdiction.US_FEDRAMP,
            allow_egress=False,
        )

        allowed = self.engine.intercept_egress_traffic(
            spec.enclave_id,
            destination_url="https://external-api.com/v1/data",
            payload_bytes=4096,
        )
        self.assertFalse(allowed)

        # Intercept second attempt
        allowed2 = self.engine.intercept_egress_traffic(
            spec.enclave_id,
            destination_url="https://s3.amazonaws.com/bucket",
            payload_bytes=1024,
        )
        self.assertFalse(allowed2)

        dash = self.engine.get_sovereignty_dashboard()
        self.assertEqual(dash["total_blocked_egress_attempts"], 2)

    def test_intercept_egress_traffic_permitted_when_egress_true(self):
        spec = self.engine.register_enclave(
            edition_id="ed-bastion",
            jurisdiction=SovereignJurisdiction.GLOBAL_STRICT,
            enclave_type=AirgapEnclaveType.BASTION_FEDERATED,
            allow_egress=True,
        )

        allowed = self.engine.intercept_egress_traffic(
            spec.enclave_id,
            destination_url="https://authorized-partner.com",
            payload_bytes=512,
        )
        self.assertTrue(allowed)

    def test_generate_and_fetch_audit_receipt(self):
        spec = self.engine.register_enclave(
            edition_id="ed-audit",
            jurisdiction=SovereignJurisdiction.CN_MLPS,
            allow_egress=False,
        )
        # Trigger 1 blocked egress
        self.engine.intercept_egress_traffic(spec.enclave_id, "https://telemetry.evil.com", 256)

        receipt = self.engine.generate_sovereignty_audit_receipt(spec.enclave_id, "ciso@elmos.io")
        self.assertIsNotNone(receipt)
        self.assertTrue(receipt.data_residency_verified)
        self.assertEqual(receipt.egress_attempt_blocked_count, 1)
        self.assertIsNotNone(receipt.signature_digest)

        fetched = self.engine.get_audit_receipt(receipt.receipt_id)
        self.assertEqual(fetched.signature_digest, receipt.signature_digest)

    def test_sovereignty_dashboard_metrics(self):
        self.engine.register_enclave("ed-1", SovereignJurisdiction.EU_GDPR, allow_egress=False)
        self.engine.register_enclave("ed-2", SovereignJurisdiction.SG_MAS, allow_egress=True)

        dash = self.engine.get_sovereignty_dashboard()
        self.assertEqual(dash["total_enclaves"], 2)
        self.assertEqual(dash["strict_airgap_enclaves"], 1)
        self.assertIn("eu_gdpr", dash["jurisdiction_breakdown"])
        self.assertIn("sg_mas", dash["jurisdiction_breakdown"])

    def test_unknown_enclave_raises_error(self):
        with self.assertRaises(ValueError):
            self.engine.intercept_egress_traffic("non-existent-enclave", "http://test.com", 100)


if __name__ == "__main__":
    unittest.main()
