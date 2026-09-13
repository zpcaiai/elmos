"""Unit and contract tests for all 22 Batch 45 Mature Product Certification skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch45"))

from b45_skill_runtime import B45SkillRuntime


@pytest.fixture
def runtime():
    return B45SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 22
    for s in runtime.SKILLS:
        assert s.startswith("b45-")


def test_b45_mature_product_certification(runtime):
    res = runtime.dispatch("b45-mature-product-certification", "certify", {})
    assert res["status"] == "MATURE_PRODUCT_CERTIFIED"
    assert res["ready"] is True
    assert res["overall_maturity_level"] == "LEVEL_5_OPTIMIZED"


def test_b45_maturity_model_editions(runtime):
    res = runtime.dispatch("b45-maturity-model-editions", "assess", {"edition": "ENTERPRISE_AIR_GAPPED"})
    assert res["status"] == "EDITION_MATURITY_ASSESSED"
    assert res["maturity_score"] == 5.0


def test_b45_edition_route_vertical_certification(runtime):
    res = runtime.dispatch("b45-edition-route-vertical-certification", "certify", {})
    assert res["status"] == "VERTICAL_ROUTE_CERTIFIED"
    assert res["sample_holdout_pass_rate"] == 1.0


def test_b45_route_breadth_certification(runtime):
    res = runtime.dispatch("b45-route-breadth-certification", "certify", {"supported_routes_count": 40})
    assert res["status"] == "ROUTE_BREADTH_CERTIFIED"
    assert res["cross_pair_conformance_rate"] == 1.0


def test_b45_functional_depth_certification(runtime):
    res = runtime.dispatch("b45-functional-depth-certification", "certify", {"feature_coverage_percent": 99.5})
    assert res["status"] == "FUNCTIONAL_DEPTH_CERTIFIED"
    assert res["edge_cases_exercised"] > 1000


def test_b45_semantic_behavior_certification(runtime):
    res = runtime.dispatch("b45-semantic-behavior-certification", "evaluate", {"mismatches": 0})
    assert res["status"] == "SEMANTIC_BEHAVIOR_CERTIFIED"
    assert res["equivalence_proven"] is True

    res_fail = runtime.dispatch("b45-semantic-behavior-certification", "evaluate", {"mismatches": 3})
    assert res_fail["status"] == "BEHAVIORAL_DIVERGENCE_DETECTED"
    assert res_fail["equivalence_proven"] is False


def test_b45_target_maintainability_certification(runtime):
    res = runtime.dispatch("b45-target-maintainability-certification", "certify", {})
    assert res["status"] == "TARGET_MAINTAINABILITY_CERTIFIED"
    assert res["sqale_rating"] == "A"


def test_b45_scale_performance_certification(runtime):
    res = runtime.dispatch("b45-scale-performance-certification", "benchmark", {})
    assert res["status"] == "SCALE_PERFORMANCE_CERTIFIED"
    assert res["memory_leak_detected"] is False


def test_b45_sre_reliability_dr_certification(runtime):
    res = runtime.dispatch("b45-sre-reliability-dr-certification", "certify", {})
    assert res["status"] == "SRE_RELIABILITY_CERTIFIED"
    assert res["dr_drill_passed"] is True


def test_b45_security_data_certification(runtime):
    res = runtime.dispatch("b45-security-data-certification", "certify", {"critical_cves": 0})
    assert res["status"] == "SECURITY_DATA_CERTIFIED"

    res_fail = runtime.dispatch("b45-security-data-certification", "certify", {"critical_cves": 1})
    assert res_fail["status"] == "SECURITY_GATE_FAILED"


def test_b45_deployment_matrix_certification(runtime):
    res = runtime.dispatch("b45-deployment-matrix-certification", "certify", {"editions_tested": 8})
    assert res["status"] == "DEPLOYMENT_MATRIX_CERTIFIED"
    assert res["zero_downtime_verified"] is True


def test_b45_developer_experience_certification(runtime):
    res = runtime.dispatch("b45-developer-experience-certification", "certify", {})
    assert res["status"] == "DEV_EXPERIENCE_CERTIFIED"
    assert res["dev_satisfaction_score"] >= 4.5


def test_b45_ecosystem_certification(runtime):
    res = runtime.dispatch("b45-ecosystem-certification", "certify", {"extensions_count": 50})
    assert res["status"] == "ECOSYSTEM_CERTIFIED"
    assert res["marketplace_signing_verified"] is True


def test_b45_customer_value_certification(runtime):
    res = runtime.dispatch("b45-customer-value-certification", "audit", {"audited_customers": 15})
    assert res["status"] == "CUSTOMER_VALUE_CERTIFIED"
    assert res["uat_acceptance_rate"] == 1.0


def test_b45_economics_profitability_certification(runtime):
    res = runtime.dispatch("b45-economics-profitability-certification", "certify", {"gross_margin": 0.78})
    assert res["status"] == "PROFITABILITY_CERTIFIED"
    assert res["margin_sustainable"] is True


def test_b45_residual_risk_register(runtime):
    res = runtime.dispatch("b45-residual-risk-register", "review", {"unresolved_critical_risks": 0})
    assert res["status"] == "RESIDUAL_RISK_ACCEPTABLE"

    res_fail = runtime.dispatch("b45-residual-risk-register", "review", {"unresolved_critical_risks": 1})
    assert res_fail["status"] == "CRITICAL_RISK_BLOCKING"


def test_b45_product_governance_accountability(runtime):
    res = runtime.dispatch("b45-product-governance-accountability", "signoff", {})
    assert res["status"] == "GOVERNANCE_APPROVED"
    assert res["governance_signoffs_complete"] is True


def test_b45_design_partner_reference_validation(runtime):
    res = runtime.dispatch("b45-design-partner-reference-validation", "validate", {})
    assert res["status"] == "DESIGN_PARTNER_VALIDATED"
    assert res["production_pilot_completed"] is True


def test_b45_independent_expert_validation(runtime):
    res = runtime.dispatch("b45-independent-expert-validation", "attest", {})
    assert res["status"] == "INDEPENDENT_EXPERT_VALIDATED"
    assert res["blind_holdout_audited"] is True


def test_b45_mature_product_evidence_pack(runtime):
    res = runtime.dispatch("b45-mature-product-evidence-pack", "seal", {"release_tag": "v3.0.0-GA"})
    assert res["status"] == "EVIDENCE_PACK_SEALED"
    assert res["evidence_digest"].startswith("sha256:")


def test_b45_mature_release_readiness(runtime):
    res = runtime.dispatch("b45-mature-release-readiness", "evaluate", {})
    assert res["status"] == "RELEASE_READY"
    assert res["overall_ready"] is True


def test_b45_mature_product_final_gate(runtime):
    res = runtime.dispatch("b45-mature-product-final-gate", "evaluate", {
        "maturityDimensionPassRate": 1.0,
        "independentReviewPassRate": 1.0,
        "unresolvedCriticalRiskCount": 0.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b45-mature-product-final-gate", "evaluate", {
        "maturityDimensionPassRate": 0.90,
        "independentReviewPassRate": 1.0,
        "unresolvedCriticalRiskCount": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b45-non-existent-skill", "check")
