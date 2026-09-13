"""Comprehensive test suite for SupplyChainComplianceFactoryEngine (B40 - Skill 1397)."""

import unittest

from elmos_mature_platform.supply_chain_compliance_factory_engine import (
    SupplyChainComplianceFactoryEngine,
)
from elmos_mature_platform.types import (
    ComplianceStandard,
    PolicyEnforcementMode,
    SupplyChainComplianceRule,
)


class TestSupplyChainComplianceFactoryComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SupplyChainComplianceFactoryEngine()

    def test_default_rules_seeded(self):
        rules = self.engine.get_rules()
        self.assertGreaterEqual(len(rules), 5)
        slsa_rules = self.engine.get_rules(standard=ComplianceStandard.SLSA_LEVEL_3)
        self.assertEqual(len(slsa_rules), 2)

    def test_register_custom_rule(self):
        custom = SupplyChainComplianceRule(
            rule_id="custom-fips-140",
            standard=ComplianceStandard.CIS_BENCHMARK,
            name="FIPS 140 Cryptographic Module",
            description="Artifact must use FIPS validated crypto library",
            enforcement_mode=PolicyEnforcementMode.BLOCK,
            required_attestations=["fips_crypto_receipt"],
            max_cve_severity="low",
            enabled=True,
        )
        rid = self.engine.register_rule(custom)
        self.assertEqual(rid, "custom-fips-140")
        rules = self.engine.get_rules(standard=ComplianceStandard.CIS_BENCHMARK)
        self.assertEqual(len(rules), 1)

    def test_evaluate_artifact_slsa_level_3_passed(self):
        report = self.engine.evaluate_artifact(
            artifact_id="pkg-auth-service-3.2.0",
            standard=ComplianceStandard.SLSA_LEVEL_3,
            present_attestations=["slsa_provenance", "in_toto_statement", "hermetic_build_receipt"],
            max_detected_cve="low",
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.score_pct, 100.0)
        self.assertEqual(len(report.violated_rules), 0)
        self.assertEqual(len(report.remediations), 0)

    def test_evaluate_artifact_slsa_missing_attestation_fails(self):
        report = self.engine.evaluate_artifact(
            artifact_id="pkg-unverified-1.0.0",
            standard=ComplianceStandard.SLSA_LEVEL_3,
            present_attestations=["slsa_provenance"],  # missing in_toto and hermetic
            max_detected_cve="none",
        )
        self.assertFalse(report.passed)
        self.assertLess(report.score_pct, 100.0)
        self.assertIn("rule-slsa-hermetic", report.violated_rules)
        self.assertGreaterEqual(len(report.remediations), 2)

    def test_evaluate_artifact_excessive_cve_severity_fails(self):
        report = self.engine.evaluate_artifact(
            artifact_id="pkg-vuln-app",
            standard=ComplianceStandard.SLSA_LEVEL_3,
            present_attestations=["slsa_provenance", "in_toto_statement", "hermetic_build_receipt"],
            max_detected_cve="critical",  # SLSA level 3 max allowed is medium
        )
        self.assertFalse(report.passed)
        self.assertIn("rule-slsa-provenance", report.violated_rules)
        self.assertTrue(any("Remediate CVEs" in rem for rem in report.remediations))

    def test_evaluate_artifact_warn_only_does_not_block_overall_pass(self):
        # SOC2 Type 2 default rule is PolicyEnforcementMode.WARN
        report = self.engine.evaluate_artifact(
            artifact_id="pkg-soc2-test",
            standard=ComplianceStandard.SOC2_TYPE2,
            present_attestations=[],  # missing merkle_audit_receipt
            max_detected_cve="none",
        )
        # Violates rule, but since enforcement is WARN, passed remains True!
        self.assertTrue(report.passed)
        self.assertEqual(report.score_pct, 0.0)
        self.assertIn("rule-soc2-audit", report.violated_rules)
        self.assertEqual(len(report.remediations), 1)

    def test_evaluate_artifact_unknown_standard_returns_100_pass(self):
        report = self.engine.evaluate_artifact(
            artifact_id="pkg-empty",
            standard=ComplianceStandard.CIS_BENCHMARK,  # no default rules unless added
            present_attestations=[],
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.score_pct, 100.0)

    def test_get_report_by_id(self):
        rep = self.engine.evaluate_artifact("art-1", ComplianceStandard.NIST_SP_800_218, ["sbom_cyclonedx"])
        fetched = self.engine.get_report(rep.report_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.artifact_id, "art-1")

    def test_compliance_dashboard_metrics(self):
        self.engine.evaluate_artifact("a1", ComplianceStandard.SLSA_LEVEL_3, ["slsa_provenance", "in_toto_statement", "hermetic_build_receipt"])
        self.engine.evaluate_artifact("a2", ComplianceStandard.SLSA_LEVEL_3, [])  # fails

        dash = self.engine.get_compliance_dashboard()
        self.assertEqual(dash["total_evaluations"], 2)
        self.assertEqual(dash["passed_evaluations"], 1)
        self.assertEqual(dash["overall_pass_rate_pct"], 50.0)
        self.assertIn("slsa_level_3", dash["by_standard"])


if __name__ == "__main__":
    unittest.main()
