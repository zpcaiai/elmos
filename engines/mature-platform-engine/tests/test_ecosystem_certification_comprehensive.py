"""Comprehensive tests for EcosystemCertificationEngine (Batch 45 - Skill 1484)."""

from datetime import datetime, timedelta, timezone
import unittest

from elmos_mature_platform.ecosystem_certification_engine import (
    EcosystemCertificationEngine,
)
from elmos_mature_platform.types import (
    EcosystemCertificationScope,
    EcosystemPartnerTier,
)


class TestEcosystemCertificationComprehensive(unittest.TestCase):
    """Test suite verifying partner ecosystem certification, compliance badges, and validity."""

    def setUp(self):
        self.engine = EcosystemCertificationEngine(validity_days=180)

    def test_register_candidate(self):
        """Verify registering partner extension candidate in uncertified state."""
        rec = self.engine.register_candidate(
            partner_id="partner-snowflake",
            extension_name="snowflake-cdc-adapter",
            version="1.2.0",
            scope=EcosystemCertificationScope.DATA_PLATFORM_PACK,
            tier=EcosystemPartnerTier.STRATEGIC_PARTNER,
        )
        self.assertTrue(rec.cert_id.startswith("eco-data-"))
        self.assertEqual(rec.partner_id, "partner-snowflake")
        self.assertFalse(rec.is_certified)
        self.assertEqual(rec.compliance_score, 0.0)

    def test_duplicate_registration_raises_error(self):
        """Verify duplicate partner candidate registration raises ValueError."""
        self.engine.register_candidate("p1", "ext1", "1.0.0", EcosystemCertificationScope.PLUGIN_ADAPTER)
        with self.assertRaises(ValueError):
            self.engine.register_candidate("p1", "ext1", "1.0.0", EcosystemCertificationScope.PLUGIN_ADAPTER)

    def test_evaluate_certification_failure_below_threshold(self):
        """Verify candidate scoring below 85% is not certified."""
        rec = self.engine.register_candidate("p-untrusted", "rough-plugin", "0.1.0", EcosystemCertificationScope.PLUGIN_ADAPTER)

        # Only schema valid (20 pts) -> fails threshold
        eval_rec = self.engine.evaluate_certification(
            rec.cert_id,
            security_clean=False,
            tests_passed=False,
            schema_valid=True,
            slsa_verified=False,
        )
        self.assertFalse(eval_rec.is_certified)
        self.assertEqual(eval_rec.compliance_score, 20.0)
        self.assertEqual(eval_rec.signature, "")
        self.assertEqual(len(eval_rec.badges), 0)

    def test_evaluate_certification_success(self):
        """Verify candidate meeting all criteria (100 pts) receives certification, signature, and badges."""
        rec = self.engine.register_candidate(
            partner_id="partner-databricks",
            extension_name="unity-catalog-connector",
            version="2.0.0",
            scope=EcosystemCertificationScope.RUNTIME_CONNECTOR,
            tier=EcosystemPartnerTier.GLOBAL_ALLIANCE,
        )
        eval_rec = self.engine.evaluate_certification(
            rec.cert_id,
            security_clean=True,
            tests_passed=True,
            schema_valid=True,
            slsa_verified=True,
            certifier_key="test-notary-key",
        )
        self.assertTrue(eval_rec.is_certified)
        self.assertEqual(eval_rec.compliance_score, 100.0)
        self.assertTrue(len(eval_rec.signature) == 64)
        self.assertEqual(len(eval_rec.badges), 4)
        self.assertTrue(self.engine.check_validity(rec.cert_id))

    def test_revoke_certification(self):
        """Verify revoking active certification clears signature and appends reason badge."""
        rec = self.engine.register_candidate("p-rev", "buggy-plugin", "1.0.0", EcosystemCertificationScope.PLUGIN_ADAPTER)
        self.engine.evaluate_certification(rec.cert_id, True, True, True, True)
        self.assertTrue(rec.is_certified)

        revoked = self.engine.revoke_certification(rec.cert_id, reason="Security vulnerability discovered")
        self.assertFalse(revoked.is_certified)
        self.assertEqual(revoked.signature, "")
        self.assertIn("REVOKED: Security vulnerability discovered", revoked.badges)
        self.assertFalse(self.engine.check_validity(rec.cert_id))

    def test_check_validity_expiration(self):
        """Verify expired certification returns False."""
        rec = self.engine.register_candidate("p-exp", "old-plugin", "1.0.0", EcosystemCertificationScope.PLUGIN_ADAPTER)
        self.engine.evaluate_certification(rec.cert_id, True, True, True, True)

        # Set expiration to the past
        rec.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.assertFalse(self.engine.check_validity(rec.cert_id))

    def test_get_ecosystem_directory(self):
        """Verify directory aggregates certified extensions by scope and tier."""
        rec = self.engine.register_candidate(
            "p-blue",
            "k8s-mesh-blueprint",
            "1.0.0",
            EcosystemCertificationScope.SOLUTION_BLUEPRINT,
            tier=EcosystemPartnerTier.VERIFIED_INTEGRATOR,
        )
        self.engine.evaluate_certification(rec.cert_id, True, True, True, True)

        dir_report = self.engine.get_ecosystem_directory()
        self.assertEqual(dir_report["active_certified_count"], 1)
        self.assertEqual(dir_report["certified_by_scope"][EcosystemCertificationScope.SOLUTION_BLUEPRINT.value], 1)
        self.assertEqual(dir_report["certified_by_tier"][EcosystemPartnerTier.VERIFIED_INTEGRATOR.value], 1)


if __name__ == "__main__":
    unittest.main()
