from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "batch40_repository_controls.py"
SPEC = importlib.util.spec_from_file_location("batch40_repository_controls", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Batch40RepositoryControlsTest(unittest.TestCase):
    def fixture(self) -> tuple[Path, Path, Path]:
        root = Path(tempfile.mkdtemp())
        repo = root / "repo"
        pack = repo / "pack"
        (repo / ".github").mkdir(parents=True)
        (repo / "config").mkdir(parents=True)
        (repo / "engine/policies").mkdir(parents=True)
        (pack / "evidence/execution").mkdir(parents=True)
        (pack / "evidence/provenance").mkdir(parents=True)
        patterns = [
            "/.github/workflows/",
            "/Makefile.batch40",
            "/config/batch40-*",
            "/docs/batch40/",
            "/engines/security-compliance-engine/",
            "/mature-product-packs/batch40/",
            "/schemas/batch40/",
            "/scripts/batch40_*",
            "/tests/batch40/",
        ]
        (repo / ".github/CODEOWNERS").write_text(
            "\n".join(f"{pattern} @owner" for pattern in patterns) + "\n",
            encoding="utf-8",
        )
        (repo / "SECURITY.md").write_text("Report privately.\n", encoding="utf-8")
        psirt = {
            "schemaVersion": 1,
            "policyId": "fixture-psirt",
            "owner": "owner",
            "privateReportingChannel": "github-security-advisory://example/repo",
            "severitySlaHours": {"critical": 24, "high": 168, "medium": 720, "low": 2160},
            "states": list(MODULE.PSIRT_STATES),
            "requiredCaseFields": [
                "caseId", "receivedAt", "severity", "owner", "affectedArtifacts", "evidenceRefs", "currentState"
            ],
            "closureRequirements": ["verify", "release", "advisory", "vex", "threat model"],
            "automaticRiskAcceptance": False,
            "automaticCaseClosure": False,
            "externalExerciseStatus": "NOT_RUN",
            "independentVerification": "NOT_RUN",
        }
        (repo / "config/psirt.json").write_text(json.dumps(psirt), encoding="utf-8")
        license_policy = {
            "schemaVersion": 1,
            "policyId": "fixture-license-review",
            "owner": "owner",
            "status": "DRAFT_NOT_APPROVED",
            "defaultDecision": "BLOCK_PENDING_REVIEW",
            "allowedLicenses": [],
            "prohibitedLicenses": [],
            "contextDependentLicenses": [],
            "decisionStatuses": [
                "PENDING_METADATA", "PENDING_APPROVAL", "APPROVED", "PROHIBITED", "CONTEXT_REVIEW_REQUIRED"
            ],
            "approvalRequirements": {"qualifiedLegalApprover": True, "approvalReference": True},
            "automaticApproval": False,
            "independentVerification": "NOT_RUN",
        }
        (repo / "config/license.json").write_text(json.dumps(license_policy), encoding="utf-8")
        adapter = {
            "defaultNetwork": "DENY",
            "secretValuesInEvidence": False,
            "productionMutationAllowed": False,
            "agentRiskAcceptanceAllowed": False,
            "adapters": ["SAST", "SCA", "IAC", "CONTAINER", "DAST", "API_SECURITY", "SBOM", "PROVENANCE", "VEX"],
            "initialStatus": "NOT_CONFIGURED",
            "activeTestAuthorizationRequired": ["DAST", "API_SECURITY"],
        }
        (repo / "engine/policies/adapters.json").write_text(json.dumps(adapter), encoding="utf-8")
        profile = {
            "criticalSystem": {
                "dualSecurityApproval": True,
                "independentAssessment": True,
                "killSwitch": True,
                "incidentGameDay": True,
                "recoveryValidation": True,
                "automaticRiskAcceptance": False,
                "automaticProductionAuthorization": False,
            },
            "frameworks": ["SLSA_1.2", "NIST_SSDF_1.1"],
        }
        (repo / "engine/policies/profiles.json").write_text(json.dumps(profile), encoding="utf-8")
        run = pack / "evidence/execution/base.json"
        run.write_text(json.dumps({"check": "base"}), encoding="utf-8")
        (pack / "evidence/provenance/base-provenance.json").write_text(json.dumps({
            "evidenceId": "base",
            "runReport": {"path": "evidence/execution/base.json", "sha256": MODULE.sha256_file(run)},
        }), encoding="utf-8")
        raw = [[
            {
                "number": 1,
                "state": "fixed",
                "dependency": {"package": {"name": "a", "ecosystem": "pip"}, "manifest_path": "a.lock"},
                "security_advisory": {"ghsa_id": "GHSA-1111-2222-3333"},
            },
            {
                "number": 2,
                "state": "dismissed",
                "dependency": {"package": {"name": "b", "ecosystem": "maven"}, "manifest_path": "pom.xml"},
                "security_advisory": {"ghsa_id": "GHSA-4444-5555-6666"},
            },
        ]]
        (pack / "evidence/execution/b40-dependabot-alerts.raw.json").write_text(json.dumps(raw), encoding="utf-8")
        (pack / "evidence/execution/b40-dependabot-alerts.json").write_text(
            json.dumps({"alertCount": 2, "openCount": 0}), encoding="utf-8"
        )
        (pack / "certification.json").write_text(json.dumps({"status": "NOT_RUN"}), encoding="utf-8")
        (pack / "evidence/execution/b40-dependency-inventory.json").write_text(json.dumps({
            "totals": {"externalComponentCount": 1},
            "components": [{
                "purl": "pkg:maven/example/a@1.0", "ecosystem": "maven", "version": "1.0",
                "internal": False, "declaredIn": ["pom.xml"],
            }],
        }), encoding="utf-8")
        config = {
            "schemaVersion": 1,
            "policyId": "fixture-controls",
            "owner": "owner",
            "codeownersPath": ".github/CODEOWNERS",
            "securityPolicyPath": "SECURITY.md",
            "psirtPolicyPath": "config/psirt.json",
            "licenseReviewPolicyPath": "config/license.json",
            "adapterPolicyPath": "engine/policies/adapters.json",
            "securityProfilePath": "engine/policies/profiles.json",
            "requiredCodeownerPatterns": patterns,
            "requiredAdapters": ["SAST", "SCA", "IAC", "CONTAINER", "DAST", "SBOM", "PROVENANCE", "VEX"],
            "modelArtifactExtensions": [".onnx"],
            "modelArtifactRegistry": {},
            "externalExecution": {key: "NOT_RUN" for key in MODULE.EXTERNAL_KEYS},
            "capabilities": list(MODULE.CAPABILITIES),
        }
        config_path = repo / "config/controls.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return repo, pack, config_path

    def analyze(self, repo: Path, pack: Path, config: Path) -> dict:
        with (
            mock.patch.object(MODULE, "git_revision", return_value="a" * 40),
            mock.patch.object(MODULE, "tracked_files", return_value=[]),
        ):
            return MODULE.analyze(repo, pack, config)

    def test_complete_local_controls_are_limited_not_certified(self) -> None:
        repo, pack, config = self.fixture()
        report = self.analyze(repo, pack, config)
        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["failedControls"])
        self.assertEqual("NOT_RUN", report["independentVerification"])
        self.assertEqual("NOT_CERTIFIED", report["certificationStatus"])
        self.assertTrue(all(item["status"] == "limited" for item in report["capabilityResults"].values()))
        vex = report["vexRecords"]
        self.assertEqual(["FIXED", "UNDER_INVESTIGATION"], [item["vexStatus"] for item in vex])
        self.assertNotIn("NOT_AFFECTED", {item["vexStatus"] for item in vex})
        self.assertEqual("PENDING_METADATA", report["licenseReviewQueue"][0]["decisionStatus"])
        self.assertIsNone(report["licenseReviewQueue"][0]["approvalRef"])

    def test_external_status_cannot_be_promoted_by_repository_config(self) -> None:
        repo, pack, config = self.fixture()
        payload = json.loads(config.read_text(encoding="utf-8"))
        payload["externalExecution"]["sast"] = "PASS"
        config.write_text(json.dumps(payload), encoding="utf-8")
        report = self.analyze(repo, pack, config)
        self.assertIn("B40-REPOSITORY-CONTROL-SCOPE", report["failedControls"])

    def test_missing_sensitive_codeowner_fails_closed(self) -> None:
        repo, pack, config = self.fixture()
        path = repo / ".github/CODEOWNERS"
        path.write_text(path.read_text(encoding="utf-8").replace("/scripts/batch40_* @owner\n", ""), encoding="utf-8")
        report = self.analyze(repo, pack, config)
        self.assertIn("B40-SECURE-REVIEW-OWNERSHIP", report["failedControls"])

    def test_tampered_provenance_fails_closed(self) -> None:
        repo, pack, config = self.fixture()
        record = pack / "evidence/provenance/base-provenance.json"
        payload = json.loads(record.read_text(encoding="utf-8"))
        payload["runReport"]["sha256"] = "sha256:" + "0" * 64
        record.write_text(json.dumps(payload), encoding="utf-8")
        report = self.analyze(repo, pack, config)
        self.assertIn("B40-CONTENT-ADDRESSED-PROVENANCE", report["failedControls"])

    def test_unregistered_model_artifact_fails_closed(self) -> None:
        repo, pack, config = self.fixture()
        with (
            mock.patch.object(MODULE, "git_revision", return_value="a" * 40),
            mock.patch.object(MODULE, "tracked_files", side_effect=[["models/a.onnx"], [], []]),
        ):
            report = MODULE.analyze(repo, pack, config)
        self.assertIn("B40-AI-MODEL-ARTIFACT-REGISTRY", report["failedControls"])

    def test_psirt_cannot_auto_close_or_accept_risk(self) -> None:
        repo, pack, config = self.fixture()
        path = repo / "config/psirt.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["automaticCaseClosure"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = self.analyze(repo, pack, config)
        self.assertIn("B40-PSIRT-LIFECYCLE", report["failedControls"])

    def test_draft_license_policy_cannot_allow_or_auto_approve(self) -> None:
        repo, pack, config = self.fixture()
        path = repo / "config/license.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["allowedLicenses"] = ["MIT"]
        payload["automaticApproval"] = True
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = self.analyze(repo, pack, config)
        self.assertIn("B40-LICENSE-DECISION-QUEUE", report["failedControls"])

    def test_assessment_identity_must_be_distinct(self) -> None:
        self.assertFalse(MODULE.identities_are_independent("same", "SAME"))
        self.assertTrue(MODULE.identities_are_independent("executor", "verifier"))


if __name__ == "__main__":
    unittest.main()
