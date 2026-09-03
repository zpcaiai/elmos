"""Comprehensive Tests for Functional Assurance & Certification Engine v4.1.0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


@pytest.fixture
def context() -> FunctionalAssuranceContext:
    return FunctionalAssuranceContext(
        tenant_id="TENANT_PROD_001",
        project_id="PROJECT_SAFETY_CRITICAL",
        execution_epoch="EPOCH_2026_01",
        fencing_token=42,
        candidate_digest="sha256:" + "c" * 64,
        base_evidence_receipt="BASE_EVIDENCE_RECEIPT_OK_VALIDATED",
        authority_digest="AUTH_DIGEST_ROOT_KEY_OK",
    )


@pytest.fixture
def kernel() -> FunctionalAssuranceKernel:
    return FunctionalAssuranceKernel()


def test_all_178_skills_dispatched(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    skills_dir = (
        REPOSITORY_ROOT
        / "skills/elmos-functional-assurance-certification-skills-v4.1.0/agent-skills/runtime"
    )
    all_skills = sorted([p.name for p in skills_dir.iterdir() if p.is_dir()])
    assert len(all_skills) == 178

    for sname in all_skills:
        res = kernel.dispatch(sname, {}, context)
        assert res.get("status") != "UNSUPPORTED", f"Skill {sname} returned UNSUPPORTED"
        assert "decision" in res or "status" in res


def test_fail_closed_missing_tenant(kernel: FunctionalAssuranceKernel) -> None:
    with pytest.raises(ValueError):
        FunctionalAssuranceContext(
            tenant_id="",
            project_id="",
            execution_epoch="EPOCH_INVALID",
            fencing_token=1,
            candidate_digest="sha256:" + "0" * 64,
            base_evidence_receipt="NONE",
            authority_digest="NONE",
        )


def test_measurement_uncertainty_budget(context: FunctionalAssuranceContext) -> None:
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
    assert expanded > 0.0
    assert budget.combined_standard_uncertainty > 0.0


def test_guard_band_decision_rule(context: FunctionalAssuranceContext) -> None:
    gb = GuardBandSpecification(
        lower_spec_limit=0.90,
        upper_spec_limit=1.0,
        rule_type=DecisionRuleType.GUARD_BAND_EXPANDED,
    )
    assert gb.evaluate_conformity(measured_value=0.95, uncertainty=0.02) == ConformityDecision.CONFORMING
    assert gb.evaluate_conformity(measured_value=0.91, uncertainty=0.02) == ConformityDecision.CONDITIONAL_CONFORMING
    assert gb.evaluate_conformity(measured_value=0.88, uncertainty=0.02) == ConformityDecision.NON_CONFORMING


def test_worm_merkle_evidence_sealer() -> None:
    items = [
        {"role": "intake_report", "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111"},
        {"role": "fuzz_receipt", "digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222"},
        {"role": "formal_proof", "digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333"},
    ]
    tree = WormMerkleTree()
    for it in items:
        tree.append(it["digest"], role=it["role"])

    root = tree.root_digest
    assert len(root) == 64
    assert len(tree.leaves) == 3
    assert tree.leaves[0].prev_leaf_hash == "08209889ed8d10767ffb780e8c5d6bd68aa3fe1e5385d93f1d8fa4e3819626ec"


def test_iso17065_impartiality_policy() -> None:
    assert not CertificationPolicyEngine.evaluate_impartiality_policy("ALICE", "ALICE")
    assert CertificationPolicyEngine.evaluate_impartiality_policy("ALICE", "BOB")


def test_certificate_issuance_and_verification(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    cert = kernel.issue_certification(
        context,
        assurance_level="E5",
        product_level="P05",
        scope_description="Mission-Critical Safety Kernel",
        evaluator_id="AUDITOR_ALICE",
        independent_reviewer_id="REVIEWER_BOB",
        sector="AVIATION",
    )
    assert cert.certificate_id.startswith("CERT-")
    assert cert.assurance_level == AssuranceLevel.E5
    assert cert.product_level == ProductAssuranceLevel.P05
    assert cert.sector == SectorType.AVIATION
    assert cert.status == CertificateStatus.ISSUED

    res = kernel.verify_certificate_record(cert.to_dict())
    assert res["signature_valid"] is True
    assert res["decision"] == ConformityDecision.CONFORMING.value


def test_certificate_database_persistence(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    db = CertificationDatabase(":memory:")
    cert = kernel.issue_certification(
        context,
        assurance_level="E4",
        product_level="P04",
        scope_description="Automotive ASIL-D Certification",
        evaluator_id="EVAL_01",
        independent_reviewer_id="REV_02",
        sector="AUTOMOTIVE",
    )
    db.save_certificate(cert)

    loaded = db.get_certificate(cert.certificate_id)
    assert loaded is not None
    assert loaded.certificate_id == cert.certificate_id
    assert loaded.assurance_level == AssuranceLevel.E4
    assert loaded.sector == SectorType.AUTOMOTIVE
    assert loaded.signature_receipt == cert.signature_receipt
    db.close()


def test_regulated_sector_profiles(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    aviation = kernel.dispatch("elmos-aviation-software-tool-formal-assurance-profile", {}, context)
    assert aviation["decision"] == ConformityDecision.CONFORMING.value
    assert aviation["standard"] == "RTCA DO-178C / EUROCAE ED-12C / DO-330"

    automotive = kernel.dispatch("elmos-automotive-functional-safety-sotif-profile", {}, context)
    assert automotive["decision"] == ConformityDecision.CONFORMING.value

    medical = kernel.dispatch("elmos-medical-device-ai-software-lifecycle-risk-profile", {}, context)
    assert medical["decision"] == ConformityDecision.CONFORMING.value

    finance = kernel.dispatch("elmos-financial-model-risk-validation-profile", {}, context)
    assert finance["decision"] == ConformityDecision.CONFORMING.value


def test_formal_proof_replay(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    res = kernel.dispatch(
        "elmos-machine-checkable-proof-replay-controller",
        {"proof_kernel": "lean4", "theorem_name": "theorem_safety_invariants", "proof_script_digest": "LEAN4_PROOF_DIGEST_OK"},
        context,
    )
    assert res["soundness_verified"] is True
    assert res["decision"] == ConformityDecision.CONFORMING.value
    assert res["assurance_level"] == "E4"


def test_confidential_ai_and_wasi_sandbox(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    tee_res = kernel.dispatch(
        "elmos-confidential-ai-inference-receipt-certifier",
        {"tee_platform": "AWS_NITRO", "enclave_measurement": "sha256:" + "1" * 64},
        context,
    )
    assert tee_res["policy_matched"] is True
    assert tee_res["decision"] == ConformityDecision.CONFORMING.value

    wasi_res = kernel.dispatch(
        "elmos-wasi-sandbox-capability-certifier",
        {"allowed_roots": ["/tmp/sandbox"], "allowed_hosts": []},
        context,
    )
    assert wasi_res["least_privilege_enforced"] is True
    assert wasi_res["decision"] == ConformityDecision.CONFORMING.value


def test_database_and_sre_operations(kernel: FunctionalAssuranceKernel, context: FunctionalAssuranceContext) -> None:
    cutover = kernel.dispatch("elmos-database-cutover-rollback-certifier", {}, context)
    assert cutover["rto_sla_met"] is True

    slo = kernel.dispatch("elmos-slo-error-budget-release-governor", {}, context)
    assert slo["release_admitted"] is True

    failover = kernel.dispatch("elmos-multi-region-active-active-failover-certifier", {}, context)
    assert failover["split_brain_prevented"] is True


def test_full_certification_campaign_workflow(context: FunctionalAssuranceContext) -> None:
    runner = CertificationWorkflowRunner()
    res = runner.run_full_certification_campaign(context, target_assurance_level="E5", sector="AVIATION")
    assert res["campaign_status"] == "COMPLETED"
    assert res["decision"] == ConformityDecision.CONFORMING.value
    assert res["certificate"]["assurance_level"] == "E5"
    assert res["certificate"]["sector"] == "AVIATION"
    assert len(res["merkle_seal"]["merkle_root_digest"]) == 64


def test_golden_routes(context: FunctionalAssuranceContext) -> None:
    validator = GoldenRouteValidator()
    assert len(validator.GOLDEN_ROUTES) == 23

    for gr in validator.GOLDEN_ROUTES:
        res = validator.validate_golden_route(gr, context)
        assert res["validated"] is True
        assert res["decision"] == ConformityDecision.CONFORMING.value


def test_cli_execution(tmp_path: Path, context: FunctionalAssuranceContext) -> None:
    cert_path = tmp_path / "cert.json"
    code = cli_main([
        "certify",
        "--candidate-digest", context.candidate_digest,
        "--tenant-id", context.tenant_id,
        "--project-id", context.project_id,
        "--assurance-level", "E4",
        "--sector", "MEDICAL",
        "--output", str(cert_path),
    ])
    assert code == 0
    assert cert_path.exists()

    # Verify certificate via CLI
    cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
    single_cert_file = tmp_path / "single_cert.json"
    single_cert_file.write_text(json.dumps(cert_data["certificate"]), encoding="utf-8")

    verify_code = cli_main(["verify-certificate", "--cert-file", str(single_cert_file)])
    assert verify_code == 0
