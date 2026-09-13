"""Comprehensive test suite for Security & Compliance engine fixtures, policies, and contracts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestSecurityFixturesAndContracts(unittest.TestCase):
    """Validates Batch 17 security policies, contract fixtures, and trust boundaries."""

    def setUp(self) -> None:
        self.fixtures_dir = ROOT / "test-fixtures"
        self.policies_dir = ROOT / "policies"

    def test_security_tool_adapters_policy(self) -> None:
        policy_file = self.policies_dir / "security-tool-adapters-v1.json"
        self.assertTrue(policy_file.exists())
        policy = json.loads(policy_file.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        self.assertEqual(policy["defaultNetwork"], "DENY")
        self.assertFalse(policy["secretValuesInEvidence"])
        self.assertFalse(policy["productionMutationAllowed"])
        self.assertFalse(policy["agentRiskAcceptanceAllowed"])
        self.assertEqual(policy["initialStatus"], "NOT_CONFIGURED")

        expected_adapters = {
            "ESTATE", "IDENTITY", "SECRET", "CRYPTO", "SAST", "SCA", "IAC",
            "CONTAINER", "DAST", "API_SECURITY", "CLOUD", "RUNTIME", "DLP",
            "SBOM", "PROVENANCE", "VEX", "OSCAL", "SIEM"
        }
        self.assertTrue(expected_adapters.issubset(set(policy["adapters"])))
        self.assertEqual(set(policy["activeTestAuthorizationRequired"]), {"DAST", "API_SECURITY"})

    def test_security_profiles_policy(self) -> None:
        policy_file = self.policies_dir / "security-profiles-v1.json"
        self.assertTrue(policy_file.exists())
        policy = json.loads(policy_file.read_text(encoding="utf-8"))

        self.assertEqual(policy["schemaVersion"], "1.0")
        expected_profiles = {"BASELINE", "STANDARD", "HIGH_ASSURANCE", "REGULATED", "CRITICAL_SYSTEM"}
        self.assertEqual(set(policy["profiles"]), expected_profiles)

        critical = policy["criticalSystem"]
        self.assertTrue(critical["dualSecurityApproval"])
        self.assertTrue(critical["independentAssessment"])
        self.assertTrue(critical["killSwitch"])
        self.assertFalse(critical["automaticRiskAcceptance"])
        self.assertFalse(critical["automaticProductionAuthorization"])

        expected_frameworks = {"NIST_CSF_2.0", "NIST_SP_800_207", "NIST_SP_800_207A", "NIST_SSDF_1.1", "OWASP_ASVS_5.0.0", "SLSA_1.2", "OSCAL"}
        self.assertEqual(set(policy["frameworks"]), expected_frameworks)

    def test_security_authorization_decision_non_self_certification(self) -> None:
        fixture_file = self.fixtures_dir / "security-authorization-decision.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("authorizationBoundaryId", data)
        self.assertIn("decision", data)
        # Non-self-certification enforcement
        self.assertTrue(data.get("internalDecisionOnly", False))
        self.assertFalse(data.get("externalCertificationGranted", True))

    def test_security_control_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "security-control.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("controlId", data)
        self.assertIn("catalogId", data)
        self.assertIn("title", data)
        self.assertIn("controlClass", data)

    def test_security_estate_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "security-estate.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("estateId", data)
        self.assertIn("organizationId", data)
        self.assertIsInstance(data["assetRefs"], list)
        self.assertIsInstance(data["trustBoundaryRefs"], list)

    def test_security_finding_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "security-finding.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("findingId", data)
        self.assertIn("assetId", data)
        self.assertIn("category", data)
        self.assertIn("severity", data)
        self.assertIn("confidence", data)

    def test_threat_model_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "threat-model.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("threatModelId", data)
        self.assertIn("methods", data)
        self.assertIsInstance(data["threatRefs"], list)

    def test_vulnerability_risk_decision_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "vulnerability-risk-decision.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("vulnerabilityId", data)
        self.assertIn("riskLevel", data)
        self.assertIn("decision", data)
        self.assertIn("reachability", data)

    def test_control_assessment_result_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "control-assessment-result.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("controlId", data)
        self.assertIn("result", data)
        self.assertIn("evidenceRefs", data)

    def test_provenance_statement_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "provenance-statement.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("provenanceId", data)
        self.assertIn("subjectDigest", data)
        self.assertIn("builderIdentity", data)
        self.assertIn("trustedBuilder", data)

    def test_sbom_document_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "sbom-document.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("sbomId", data)
        self.assertIn("format", data)
        self.assertIn("subjectDigest", data)
        self.assertIn("componentRefs", data)

    def test_batch17_acceptance_scenarios_fixture(self) -> None:
        fixture_file = self.fixtures_dir / "batch17-acceptance-scenarios.json"
        self.assertTrue(fixture_file.exists())
        data = json.loads(fixture_file.read_text(encoding="utf-8"))

        self.assertIn("scenarios", data)
        self.assertTrue(len(data["scenarios"]) > 0)
        for s in data["scenarios"]:
            self.assertIn("id", s)
            self.assertIn("expected", s)


if __name__ == "__main__":
    unittest.main()
