"""Comprehensive tests for Service layer, Workflows, Policies, and Golden Routes."""

from __future__ import annotations

import unittest

from elmos_functional_assurance.domain import (
    ConformityDecision,
    FunctionalAssuranceContext,
    SectorType,
)
from elmos_functional_assurance.golden_routes import GoldenRouteValidator
from elmos_functional_assurance.kernel import FunctionalAssuranceKernel
from elmos_functional_assurance.policies import CertificationPolicyEngine
from elmos_functional_assurance.service import FunctionalAssuranceService
from elmos_functional_assurance.workflows import CertificationWorkflowRunner


class TestServiceWorkflowsAndPolicies(unittest.TestCase):
    """Tests for Policy Engine, Golden Routes, Workflows, and High-level Service."""

    def setUp(self) -> None:
        self.context = FunctionalAssuranceContext(
            tenant_id="TENANT_TEST_SERVICE",
            project_id="PROJ_TEST_SERVICE",
            execution_epoch="EPOCH_2026_01",
            fencing_token=10,
            candidate_digest="sha256:" + "f" * 64,
            base_evidence_receipt="REC_BASE_TEST",
            authority_digest="AUTH_ROOT_TEST",
        )

    # ── Policy Engine Tests ──

    def test_impartiality_policy(self) -> None:
        # Different auditor and reviewer
        self.assertTrue(CertificationPolicyEngine.evaluate_impartiality_policy("AUDITOR_1", "REVIEWER_2"))
        # Same auditor and reviewer
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy("AUDITOR_1", "AUDITOR_1"))
        # Same with whitespace
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy(" AUDITOR_1 ", "AUDITOR_1"))
        # Empty values
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy("", "REVIEWER_2"))
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy("AUDITOR_1", ""))
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy("", ""))

    def test_tenant_isolation_policy(self) -> None:
        # Same tenant
        self.assertTrue(CertificationPolicyEngine.evaluate_tenant_isolation_policy(self.context, "TENANT_TEST_SERVICE"))
        # Different tenant
        self.assertFalse(CertificationPolicyEngine.evaluate_tenant_isolation_policy(self.context, "TENANT_OTHER"))
        # Empty tenant
        self.assertFalse(CertificationPolicyEngine.evaluate_tenant_isolation_policy(self.context, ""))

    def test_assurance_level_policy_monotonicity(self) -> None:
        # Equal levels
        self.assertTrue(CertificationPolicyEngine.evaluate_assurance_level_policy("E3", "E3"))
        # Higher level meets lower requirement
        self.assertTrue(CertificationPolicyEngine.evaluate_assurance_level_policy("E5", "E4"))
        self.assertTrue(CertificationPolicyEngine.evaluate_assurance_level_policy("E4", "E1"))
        self.assertTrue(CertificationPolicyEngine.evaluate_assurance_level_policy("E1", "E0"))
        # Lower level cannot satisfy higher requirement
        self.assertFalse(CertificationPolicyEngine.evaluate_assurance_level_policy("E3", "E4"))
        self.assertFalse(CertificationPolicyEngine.evaluate_assurance_level_policy("E0", "E5"))
        # Invalid levels
        self.assertFalse(CertificationPolicyEngine.evaluate_assurance_level_policy("E6", "E4"))
        self.assertFalse(CertificationPolicyEngine.evaluate_assurance_level_policy("E4", "INVALID"))
        self.assertFalse(CertificationPolicyEngine.evaluate_assurance_level_policy("", "E2"))

    # ── Golden Route Validator Tests ──

    def test_golden_routes_complete_validation(self) -> None:
        validator = GoldenRouteValidator()
        self.assertEqual(len(validator.GOLDEN_ROUTES), 23)

        for route in validator.GOLDEN_ROUTES:
            res = validator.validate_golden_route(route, self.context)
            self.assertEqual(res["golden_route"], route)
            self.assertTrue(res["validated"])
            self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)
            self.assertIn("details", res)

    def test_golden_route_unknown_route_raises_error(self) -> None:
        validator = GoldenRouteValidator()
        with self.assertRaises(ValueError) as cm:
            validator.validate_golden_route("nonexistent-unregistered-route", self.context)
        self.assertIn("Unknown golden route", str(cm.exception))

    def test_golden_route_validator_custom_kernel(self) -> None:
        custom_kernel = FunctionalAssuranceKernel(key_id="CUSTOM_KEY_123")
        validator = GoldenRouteValidator(kernel=custom_kernel)
        self.assertIs(validator.kernel, custom_kernel)
        res = validator.validate_golden_route("slsa-l3-hermetic-build-route", self.context)
        self.assertTrue(res["validated"])

    # ── Certification Workflow Runner Tests ──

    def test_campaign_with_aviation_sector(self) -> None:
        runner = CertificationWorkflowRunner()
        res = runner.run_full_certification_campaign(
            self.context, target_assurance_level="E5", sector="AVIATION"
        )
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(res["certificate"]["assurance_level"], "E5")
        self.assertEqual(res["certificate"]["product_level"], "P04")
        self.assertEqual(res["certificate"]["sector"], "AVIATION")
        self.assertEqual(len(res["merkle_seal"]["merkle_root_digest"]), 64)
        self.assertTrue(res["merkle_seal"]["integrity_verified"])

    def test_campaign_with_medical_sector(self) -> None:
        runner = CertificationWorkflowRunner()
        res = runner.run_full_certification_campaign(
            self.context, target_assurance_level="E4", sector="MEDICAL"
        )
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["certificate"]["assurance_level"], "E4")
        self.assertEqual(res["certificate"]["product_level"], "P04")
        self.assertEqual(res["certificate"]["sector"], "MEDICAL")

    def test_campaign_with_automotive_sector(self) -> None:
        runner = CertificationWorkflowRunner()
        res = runner.run_full_certification_campaign(
            self.context, target_assurance_level="E3", sector="AUTOMOTIVE"
        )
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["certificate"]["assurance_level"], "E3")
        self.assertEqual(res["certificate"]["sector"], "AUTOMOTIVE")

    def test_campaign_without_sector(self) -> None:
        runner = CertificationWorkflowRunner()
        res = runner.run_full_certification_campaign(
            self.context, target_assurance_level="E2", sector=None
        )
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["certificate"]["assurance_level"], "E2")
        self.assertEqual(res["certificate"]["product_level"], "P03")
        self.assertIsNone(res["certificate"]["sector"])

    # ── Functional Assurance Service Tests ──

    def test_service_run_certification_explicit_params(self) -> None:
        service = FunctionalAssuranceService()
        payload = {
            "tenant_id": "TENANT_SRV_01",
            "project_id": "PROJ_SRV_01",
            "execution_epoch": "EPOCH_2026_SRV",
            "fencing_token": 99,
            "candidate_digest": "sha256:" + "e" * 64,
            "base_evidence_receipt=" : "BASE_REC_99",
            "authority_digest": "AUTH_DIGEST_99",
            "target_assurance_level": "E4",
            "sector": "AVIATION",
        }
        res = service.run_certification(payload)
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(res["certificate"]["tenant_id"], "TENANT_SRV_01")
        self.assertEqual(res["certificate"]["project_id"], "PROJ_SRV_01")
        self.assertEqual(res["certificate"]["assurance_level"], "E4")
        self.assertEqual(res["certificate"]["sector"], "AVIATION")

    def test_service_run_certification_defaults(self) -> None:
        service = FunctionalAssuranceService()
        payload = {
            "tenant_id": "TENANT_SRV_DEF",
            "project_id": "PROJ_SRV_DEF",
            "candidate_digest": "sha256:" + "d" * 64,
        }
        res = service.run_certification(payload)
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["certificate"]["assurance_level"], "E4")
        self.assertIsNone(res["certificate"]["sector"])


if __name__ == "__main__":
    unittest.main()
