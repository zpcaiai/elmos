"""Comprehensive tests for DesignPartnerReferenceValidationEngine (Batch 45 - Skill 1482)."""

import unittest

from elmos_mature_platform.design_partner_reference_validation_engine import (
    DesignPartnerReferenceValidationEngine,
)
from elmos_mature_platform.types import (
    DesignPartnerPhase,
)


class TestDesignPartnerReferenceValidationComprehensive(unittest.TestCase):
    """Test suite verifying design partner validation, formal sign-off, and reference publishing."""

    def setUp(self):
        self.engine = DesignPartnerReferenceValidationEngine()

    def test_create_study_initializes_onboarding(self):
        """Verify new partner study begins in ONBOARDING phase."""
        study = self.engine.create_study(
            partner_name="Global Retail Corp",
            industry="Retail",
            source_platform="Monolith Java 8",
            target_platform="Spring Boot 4 Cloud",
            lead_sponsor="VP Engineering",
        )
        self.assertTrue(study.study_id.startswith("study-"))
        self.assertEqual(study.partner_name, "Global Retail Corp")
        self.assertEqual(study.phase, DesignPartnerPhase.ONBOARDING)
        self.assertFalse(study.formal_acceptance_signed)
        self.assertEqual(len(study.criteria), 0)

    def test_add_criterion_and_record_results(self):
        """Verify adding criteria and recording pass/fail verification results."""
        study = self.engine.create_study("FinTech Partner", "Banking", "Cobol", "Java 21")
        crit1 = self.engine.add_acceptance_criterion(
            study.study_id,
            description="Transaction throughput parity",
            target_metric=">= 5000 TPS",
        )
        self.assertTrue(crit1.criterion_id.startswith("crit-"))
        self.assertFalse(crit1.passed)

        # Record empirical result
        updated_crit = self.engine.record_criterion_result(
            study.study_id,
            crit1.criterion_id,
            actual_metric="5400 TPS",
            passed=True,
        )
        self.assertTrue(updated_crit.passed)
        self.assertEqual(updated_crit.actual_metric, "5400 TPS")

    def test_phase_advancement_enforces_sequence(self):
        """Verify phase advancement cannot skip steps in the lifecycle."""
        study = self.engine.create_study("Partner A", "SaaS", "Flask", "FastAPI")

        # ONBOARDING -> PILOT_EXECUTION is valid
        self.engine.advance_phase(study.study_id, DesignPartnerPhase.PILOT_EXECUTION)
        self.assertEqual(study.phase, DesignPartnerPhase.PILOT_EXECUTION)

        # Skipping from PILOT_EXECUTION directly to REFERENCE_PUBLISHED must raise ValueError
        with self.assertRaises(ValueError):
            self.engine.advance_phase(study.study_id, DesignPartnerPhase.REFERENCE_PUBLISHED)

    def test_sign_formal_acceptance_blocked_if_criteria_unmet(self):
        """Verify sign-off is rejected if any acceptance criteria have not passed."""
        study = self.engine.create_study("Partner B", "Healthcare", "WCF", "gRPC")
        crit = self.engine.add_acceptance_criterion(study.study_id, "Latency < 50ms", "< 50ms")
        self.engine.record_criterion_result(study.study_id, crit.criterion_id, "80ms", passed=False)

        with self.assertRaises(ValueError):
            self.engine.sign_formal_acceptance(study.study_id, lead_sponsor="CTO", roi_savings_pct=35.0)

    def test_sign_formal_acceptance_and_publish_reference(self):
        """Verify full lifecycle from passing criteria to formal sign-off and reference publication."""
        study = self.engine.create_study("Logistics Co", "Logistics", "SAP ABAP", "Go Cloud")
        crit = self.engine.add_acceptance_criterion(study.study_id, "Zero data loss", "100% parity")
        self.engine.record_criterion_result(study.study_id, crit.criterion_id, "100% verified", passed=True)

        # Formal sign-off
        signed = self.engine.sign_formal_acceptance(
            study.study_id,
            lead_sponsor="VP Logistics",
            roi_savings_pct=42.5,
        )
        self.assertTrue(signed.formal_acceptance_signed)
        self.assertEqual(signed.phase, DesignPartnerPhase.ACCEPTANCE_SIGNED)
        self.assertEqual(signed.roi_savings_pct, 42.5)

        # Publish reference
        published = self.engine.publish_reference_case(
            study.study_id,
            testimonial_quote="Elmos delivered 42.5% cost reduction and zero migration downtime.",
        )
        self.assertEqual(published["status"], "REFERENCE_PUBLISHED")
        self.assertEqual(published["partner_name"], "Logistics Co")

    def test_get_fleet_roi_metrics(self):
        """Verify fleet-wide ROI aggregation across completed studies."""
        study1 = self.engine.create_study("P1", "Retail", "Legacy", "Target")
        c1 = self.engine.add_acceptance_criterion(study1.study_id, "C1", "T1")
        self.engine.record_criterion_result(study1.study_id, c1.criterion_id, "OK", True)
        self.engine.sign_formal_acceptance(study1.study_id, "Sponsor 1", 30.0)

        study2 = self.engine.create_study("P2", "Banking", "Legacy", "Target")
        c2 = self.engine.add_acceptance_criterion(study2.study_id, "C2", "T2")
        self.engine.record_criterion_result(study2.study_id, c2.criterion_id, "OK", True)
        self.engine.sign_formal_acceptance(study2.study_id, "Sponsor 2", 50.0)

        metrics = self.engine.get_fleet_roi_metrics()
        self.assertEqual(metrics["total_partners"], 2)
        self.assertEqual(metrics["signed_partners_count"], 2)
        self.assertEqual(metrics["average_roi_savings_pct"], 40.0)


if __name__ == "__main__":
    unittest.main()
