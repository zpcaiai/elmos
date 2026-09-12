"""Unit and contract tests for all 24 Batch 40 Security, Supply Chain & Compliance skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch40"))

from b40_skill_runtime import B40SkillRuntime


@pytest.fixture
def runtime():
    return B40SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 24
    for s in runtime.SKILLS:
        assert s.startswith("b40-")


def test_b40_supply_chain_compliance_factory(runtime):
    res = runtime.dispatch("b40-supply-chain-compliance-factory", "init", {})
    assert res["status"] == "SUPPLY_CHAIN_FACTORY_ONLINE"
    assert "SLSA-Level-3" in res["standards_supported"]


def test_b40_threat_modeling(runtime):
    res = runtime.dispatch("b40-threat-modeling", "model", {"system_name": "worker-pool"})
    assert res["status"] == "THREAT_MODEL_CERTIFIED"
    assert res["threats_identified"] == 12


def test_b40_security_architecture_review(runtime):
    res = runtime.dispatch("b40-security-architecture-review", "review", {"service_name": "auth-hub"})
    assert res["status"] == "SECURITY_ARCH_REVIEW_COMPLETED"
    assert res["approval_status"] == "APPROVED"


def test_b40_secure_sdlc_ssdf(runtime):
    res = runtime.dispatch("b40-secure-sdlc-ssdf", "audit", {})
    assert res["status"] == "SSDF_COMPLIANT"
    assert res["conformance_score"] == 1.0


def test_b40_sast_integration(runtime):
    res = runtime.dispatch("b40-sast-integration", "scan", {"critical_vulns": 0, "high_vulns": 0})
    assert res["status"] == "SAST_PASSED"

    res_fail = runtime.dispatch("b40-sast-integration", "scan", {"critical_vulns": 1, "high_vulns": 0})
    assert res_fail["status"] == "SAST_FAILED"


def test_b40_dast_iast_integration(runtime):
    res = runtime.dispatch("b40-dast-iast-integration", "scan", {"endpoints_tested": 40})
    assert res["status"] == "DAST_SCAN_CLEAN"
    assert res["injection_flaws"] == 0


def test_b40_secret_credential_scanning(runtime):
    res = runtime.dispatch("b40-secret-credential-scanning", "scan", {"secrets_found": 0})
    assert res["status"] == "SECRET_SCAN_PASSED"

    res_fail = runtime.dispatch("b40-secret-credential-scanning", "scan", {"secrets_found": 2})
    assert res_fail["status"] == "SECRET_DETECTED_BLOCKED"


def test_b40_container_kubernetes_iac_scanning(runtime):
    res = runtime.dispatch("b40-container-kubernetes-iac-scanning", "scan", {})
    assert res["status"] == "IAC_CONTAINER_HARDENED"
    assert res["cis_k8s_benchmark_passed"] is True


def test_b40_dependency_sca_governance(runtime):
    res = runtime.dispatch("b40-dependency-sca-governance", "scan", {"ecosystem": "cargo"})
    assert res["status"] == "SCA_APPROVED"
    assert res["cve_critical_count"] == 0


def test_b40_sbom_component_identity(runtime):
    res = runtime.dispatch("b40-sbom-component-identity", "generate", {"artifact": "kernel.tar.gz"})
    assert res["status"] == "SBOM_GENERATED_AND_VALIDATED"
    assert res["format"] == "CycloneDX-JSON-1.5"


def test_b40_slsa_provenance(runtime):
    res = runtime.dispatch("b40-slsa-provenance", "generate", {"target_level": 3})
    assert res["status"] == "SLSA_PROVENANCE_VERIFIED"
    assert res["slsa_level"] == 3


def test_b40_artifact_container_signing(runtime):
    res = runtime.dispatch("b40-artifact-container-signing", "sign", {"image_ref": "prod/app:v1"})
    assert res["status"] == "CONTAINER_SIGNED_AND_VERIFIED"
    assert res["signature_digest"].startswith("sha256:")


def test_b40_isolated_trusted_builder(runtime):
    res = runtime.dispatch("b40-isolated-trusted-builder", "build", {})
    assert res["status"] == "ISOLATED_BUILD_ENVIRONMENT_SECURED"
    assert res["tpm_measured_boot"] is True


def test_b40_ai_model_supply_chain(runtime):
    res = runtime.dispatch("b40-ai-model-supply-chain", "verify", {"model_name": "claude-3-5-sonnet"})
    assert res["status"] == "MODEL_SUPPLY_CHAIN_VERIFIED"
    assert res["safetensors_format_enforced"] is True


def test_b40_runner_update_supply_chain(runtime):
    res = runtime.dispatch("b40-runner-update-supply-chain", "verify_channel", {"channel": "stable"})
    assert res["status"] == "RUNNER_UPDATE_AUTHORIZED"
    assert res["rollback_package_staged"] is True


def test_b40_license_ip_provenance(runtime):
    res = runtime.dispatch("b40-license-ip-provenance", "scan", {"disallowed_found": 0})
    assert res["status"] == "LICENSE_COMPLIANT"

    res_fail = runtime.dispatch("b40-license-ip-provenance", "scan", {"disallowed_found": 1})
    assert res_fail["status"] == "LICENSE_NON_COMPLIANT"


def test_b40_vex_applicability(runtime):
    res = runtime.dispatch("b40-vex-applicability", "assess", {"cve_id": "CVE-2026-9999"})
    assert res["status"] == "VEX_EVALUATION_RECORDED"
    assert res["analysis_status"] == "NOT_AFFECTED"


def test_b40_vulnerability_patch_sla(runtime):
    res = runtime.dispatch("b40-vulnerability-patch-sla", "track", {"severity": "CRITICAL", "actual_hours": 24})
    assert res["status"] == "PATCH_SLA_MET"
    assert res["sla_met"] is True

    res_breach = runtime.dispatch("b40-vulnerability-patch-sla", "track", {"severity": "CRITICAL", "actual_hours": 72})
    assert res_breach["status"] == "PATCH_SLA_BREACHED"


def test_b40_psirt_security_incident(runtime):
    res = runtime.dispatch("b40-psirt-security-incident", "coordinate", {"advisory_id": "ELMOS-01"})
    assert res["status"] == "PSIRT_RESPONSE_COORDINATED"
    assert res["cve_reserved"] is True


def test_b40_compliance_control_crosswalk(runtime):
    res = runtime.dispatch("b40-compliance-control-crosswalk", "crosswalk", {})
    assert res["status"] == "COMPLIANCE_CROSSWALK_COMPLETE"
    assert len(res["frameworks"]) == 4


def test_b40_customer_audit_evidence(runtime):
    res = runtime.dispatch("b40-customer-audit-evidence", "package", {"scope": "SOC2"})
    assert res["status"] == "AUDIT_EVIDENCE_READY"
    assert res["chain_of_custody_verified"] is True


def test_b40_independent_security_assessment(runtime):
    res = runtime.dispatch("b40-independent-security-assessment", "attest", {})
    assert res["status"] == "INDEPENDENT_ASSESSMENT_PASSED"
    assert res["zero_day_findings"] == 0


def test_b40_secure_code_review_approval(runtime):
    res = runtime.dispatch("b40-secure-code-review-approval", "approve", {"pr_number": 105})
    assert res["status"] == "SECURITY_REVIEW_APPROVED"
    assert res["signed_approval"] is True


def test_b40_security_supply_chain_gate(runtime):
    res = runtime.dispatch("b40-security-supply-chain-gate", "evaluate", {
        "supplyChainCoverageRate": 0.98,
        "signaturePassRate": 1.0,
        "criticalVulnerabilityCount": 0.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b40-security-supply-chain-gate", "evaluate", {
        "supplyChainCoverageRate": 0.90,
        "signaturePassRate": 1.0,
        "criticalVulnerabilityCount": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b40-non-existent-skill", "check")
