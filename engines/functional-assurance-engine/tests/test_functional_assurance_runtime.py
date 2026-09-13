"""Comprehensive Tests for Functional Assurance & Certification Engine v4.1.0."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from elmos_functional_assurance.domain import (
    AssuranceLevel,
    CertificateStatus,
    ConformityDecision,
    DecisionRuleType,
    FunctionalAssuranceContext,
    GuardBandSpecification,
    MeasurementUncertaintyBudget,
    ProductAssuranceLevel,
    SectorType,
    UncertaintyComponent,
    WormMerkleTree,
)
from elmos_functional_assurance.database import CertificationDatabase
from elmos_functional_assurance.golden_routes import GoldenRouteValidator
from elmos_functional_assurance.kernel import FunctionalAssuranceKernel
from elmos_functional_assurance.policies import CertificationPolicyEngine
from elmos_functional_assurance.workflows import CertificationWorkflowRunner
from elmos_functional_assurance.cli import main as cli_main

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TestFunctionalAssuranceRuntime(unittest.TestCase):
    """Runtime and integration tests for Functional Assurance & Certification."""

    def setUp(self) -> None:
        self.context = FunctionalAssuranceContext(
            tenant_id="TENANT_PROD_001",
            project_id="PROJECT_SAFETY_CRITICAL",
            execution_epoch="EPOCH_2026_01",
            fencing_token=42,
            candidate_digest="sha256:" + "c" * 64,
            base_evidence_receipt="BASE_EVIDENCE_RECEIPT_OK_VALIDATED",
            authority_digest="AUTH_DIGEST_ROOT_KEY_OK",
        )
        self.kernel = FunctionalAssuranceKernel()

    def test_all_178_skills_dispatched(self) -> None:
        skills_dir = (
            REPOSITORY_ROOT
            / "skills/elmos-functional-assurance-certification-skills-v4.1.0/agent-skills/runtime"
        )
        all_skills = sorted([p.name for p in skills_dir.iterdir() if p.is_dir()])
        self.assertEqual(len(all_skills), 178)

        for sname in all_skills:
            res = self.kernel.dispatch(sname, {}, self.context)
            self.assertNotEqual(res.get("status"), "UNSUPPORTED", f"Skill {sname} returned UNSUPPORTED")
            self.assertTrue("decision" in res or "status" in res)

    def test_fail_closed_missing_tenant(self) -> None:
        with self.assertRaises(ValueError):
            FunctionalAssuranceContext(
                tenant_id="",
                project_id="",
                execution_epoch="EPOCH_INVALID",
                fencing_token=1,
                candidate_digest="sha256:" + "0" * 64,
                base_evidence_receipt="NONE",
                authority_digest="NONE",
            )

    def test_measurement_uncertainty_budget(self) -> None:
        components = [
            UncertaintyComponent(name="quantization", value=0.002, distribution="RECTANGULAR"),
            UncertaintyComponent(name="finite_sample", value=0.004, distribution="NORMAL"),
        ]
        budget = MeasurementUncertaintyBudget(
            measurand="model_accuracy",
            nominal_value=0.965,
            components=components,
            coverage_factor_k=2.0,
        )
        expanded = budget.expanded_uncertainty
        self.assertGreater(expanded, 0.0)
        self.assertGreater(budget.combined_standard_uncertainty, 0.0)

    def test_guard_band_decision_rule(self) -> None:
        gb = GuardBandSpecification(
            lower_spec_limit=0.90,
            upper_spec_limit=1.0,
            rule_type=DecisionRuleType.GUARD_BAND_EXPANDED,
        )
        self.assertEqual(gb.evaluate_conformity(measured_value=0.95, uncertainty=0.02), ConformityDecision.CONFORMING)
        self.assertEqual(gb.evaluate_conformity(measured_value=0.91, uncertainty=0.02), ConformityDecision.CONDITIONAL_CONFORMING)
        self.assertEqual(gb.evaluate_conformity(measured_value=0.88, uncertainty=0.02), ConformityDecision.NON_CONFORMING)

    def test_worm_merkle_evidence_sealer(self) -> None:
        items = [
            {"role": "intake_report", "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111"},
            {"role": "fuzz_receipt", "digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222"},
            {"role": "formal_proof", "digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333"},
        ]
        tree = WormMerkleTree()
        for it in items:
            tree.append(it["digest"], role=it["role"])

        root = tree.root_digest
        self.assertEqual(len(root), 64)
        self.assertEqual(len(tree.leaves), 3)
        self.assertEqual(tree.leaves[0].prev_leaf_hash, "08209889ed8d10767ffb780e8c5d6bd68aa3fe1e5385d93f1d8fa4e3819626ec")

    def test_iso17065_impartiality_policy(self) -> None:
        self.assertFalse(CertificationPolicyEngine.evaluate_impartiality_policy("ALICE", "ALICE"))
        self.assertTrue(CertificationPolicyEngine.evaluate_impartiality_policy("ALICE", "BOB"))

    def test_certificate_issuance_and_verification(self) -> None:
        cert = self.kernel.issue_certification(
            self.context,
            assurance_level="E5",
            product_level="P05",
            scope_description="Mission-Critical Safety Kernel",
            evaluator_id="AUDITOR_ALICE",
            independent_reviewer_id="REVIEWER_BOB",
            sector="AVIATION",
        )
        self.assertTrue(cert.certificate_id.startswith("CERT-"))
        self.assertEqual(cert.assurance_level, AssuranceLevel.E5)
        self.assertEqual(cert.product_level, ProductAssuranceLevel.P05)
        self.assertEqual(cert.sector, SectorType.AVIATION)
        self.assertEqual(cert.status, CertificateStatus.ISSUED)

        res = self.kernel.verify_certificate_record(cert.to_dict())
        self.assertTrue(res["signature_valid"])
        self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)

    def test_certificate_database_persistence(self) -> None:
        db = CertificationDatabase(":memory:")
        cert = self.kernel.issue_certification(
            self.context,
            assurance_level="E4",
            product_level="P04",
            scope_description="Automotive ASIL-D Certification",
            evaluator_id="EVAL_01",
            independent_reviewer_id="REV_02",
            sector="AUTOMOTIVE",
        )
        db.save_certificate(cert)

        loaded = db.get_certificate(cert.certificate_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.certificate_id, cert.certificate_id)
        self.assertEqual(loaded.assurance_level, AssuranceLevel.E4)
        self.assertEqual(loaded.sector, SectorType.AUTOMOTIVE)
        self.assertEqual(loaded.signature_receipt, cert.signature_receipt)
        db.close()

    def test_regulated_sector_profiles(self) -> None:
        aviation = self.kernel.dispatch("elmos-aviation-software-tool-formal-assurance-profile", {}, self.context)
        self.assertEqual(aviation["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(aviation["standard"], "RTCA DO-178C / EUROCAE ED-12C / DO-330")

        automotive = self.kernel.dispatch("elmos-automotive-functional-safety-sotif-profile", {}, self.context)
        self.assertEqual(automotive["decision"], ConformityDecision.CONFORMING.value)

        medical = self.kernel.dispatch("elmos-medical-device-ai-software-lifecycle-risk-profile", {}, self.context)
        self.assertEqual(medical["decision"], ConformityDecision.CONFORMING.value)

        finance = self.kernel.dispatch("elmos-financial-model-risk-validation-profile", {}, self.context)
        self.assertEqual(finance["decision"], ConformityDecision.CONFORMING.value)

    def test_formal_proof_replay(self) -> None:
        res = self.kernel.dispatch(
            "elmos-machine-checkable-proof-replay-controller",
            {"proof_kernel": "lean4", "theorem_name": "theorem_safety_invariants", "proof_script_digest": "LEAN4_PROOF_DIGEST_OK"},
            self.context,
        )
        self.assertTrue(res["soundness_verified"])
        self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(res["assurance_level"], "E4")

    def test_confidential_ai_and_wasi_sandbox(self) -> None:
        tee_res = self.kernel.dispatch(
            "elmos-confidential-ai-inference-receipt-certifier",
            {"tee_platform": "AWS_NITRO", "enclave_measurement": "sha256:" + "1" * 64},
            self.context,
        )
        self.assertTrue(tee_res["policy_matched"])
        self.assertEqual(tee_res["decision"], ConformityDecision.CONFORMING.value)

        wasi_res = self.kernel.dispatch(
            "elmos-wasi-sandbox-capability-certifier",
            {"allowed_roots": ["/tmp/sandbox"], "allowed_hosts": []},
            self.context,
        )
        self.assertTrue(wasi_res["least_privilege_enforced"])
        self.assertEqual(wasi_res["decision"], ConformityDecision.CONFORMING.value)

    def test_database_and_sre_operations(self) -> None:
        cutover = self.kernel.dispatch("elmos-database-cutover-rollback-certifier", {}, self.context)
        self.assertTrue(cutover["rto_sla_met"])

        slo = self.kernel.dispatch("elmos-slo-error-budget-release-governor", {}, self.context)
        self.assertTrue(slo["release_admitted"])

        failover = self.kernel.dispatch("elmos-multi-region-active-active-failover-certifier", {}, self.context)
        self.assertTrue(failover["split_brain_prevented"])

    def test_full_certification_campaign_workflow(self) -> None:
        runner = CertificationWorkflowRunner()
        res = runner.run_full_certification_campaign(self.context, target_assurance_level="E5", sector="AVIATION")
        self.assertEqual(res["campaign_status"], "COMPLETED")
        self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(res["certificate"]["assurance_level"], "E5")
        self.assertEqual(res["certificate"]["sector"], "AVIATION")
        self.assertEqual(len(res["merkle_seal"]["merkle_root_digest"]), 64)

    def test_golden_routes(self) -> None:
        validator = GoldenRouteValidator()
        self.assertEqual(len(validator.GOLDEN_ROUTES), 23)

        for gr in validator.GOLDEN_ROUTES:
            res = validator.validate_golden_route(gr, self.context)
            self.assertTrue(res["validated"])
            self.assertEqual(res["decision"], ConformityDecision.CONFORMING.value)

    def test_cli_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()
            cert_path = tmp_path / "cert.json"
            code = cli_main([
                "certify",
                "--candidate-digest", self.context.candidate_digest,
                "--tenant-id", self.context.tenant_id,
                "--project-id", self.context.project_id,
                "--assurance-level", "E4",
                "--sector", "MEDICAL",
                "--output", str(cert_path),
            ])
            self.assertEqual(code, 0)
            self.assertTrue(cert_path.exists())

            # Verify certificate via CLI
            cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
            single_cert_file = tmp_path / "single_cert.json"
            single_cert_file.write_text(json.dumps(cert_data["certificate"]), encoding="utf-8")

            verify_code = cli_main(["verify-certificate", "--cert-file", str(single_cert_file)])
            self.assertEqual(verify_code, 0)


if __name__ == "__main__":
    unittest.main()
