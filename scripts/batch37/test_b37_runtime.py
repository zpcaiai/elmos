"""Test suite verifying all 36 Batch 37 Marketplace skills in B37SkillRuntime."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from scripts.batch37.b37_skill_runtime import B37SkillRuntime


@pytest.fixture
def runtime():
    return B37SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 36
    for s in runtime.SKILLS:
        assert s.startswith("b37-")


def test_b37_extension_marketplace_factory(runtime):
    res = runtime.dispatch("b37-extension-marketplace-factory", "init", {"marketplace_id": "mkt-1"})
    assert res["factory_id"] == "fac-mkt-mkt-1"
    assert "catalog" in res["subsystems"]
    assert res["status"] == "INITIALIZED"


def test_b37_language_adapter_sdk(runtime):
    res = runtime.dispatch("b37-language-adapter-sdk", "query", {"language": "kotlin"})
    assert res["language"] == "kotlin"
    assert "Parser" in res["interfaces"]


def test_b37_framework_adapter_sdk(runtime):
    res = runtime.dispatch("b37-framework-adapter-sdk", "query", {"framework": "django"})
    assert res["framework"] == "django"
    assert "Fingerprinter" in res["interfaces"]


def test_b37_transformation_recipe_sdk(runtime):
    res = runtime.dispatch("b37-transformation-recipe-sdk", "query", {"recipe_name": "rewrite"})
    assert res["recipe_name"] == "rewrite"
    assert "RewriteRule" in res["interfaces"]


def test_b37_comparator_normalizer_sdk(runtime):
    res = runtime.dispatch("b37-comparator-normalizer-sdk", "query", {"domain": "sql"})
    assert res["domain"] == "sql"
    assert "MaskVolatiles" in res["normalizers"]


def test_b37_evidence_collector_sdk(runtime):
    res = runtime.dispatch("b37-evidence-collector-sdk", "collect", {"artifacts": ["a.txt", "b.txt"]})
    assert res["collected_count"] == 2
    assert res["immutable"] is True


def test_b37_policy_extension_sdk(runtime):
    res = runtime.dispatch("b37-policy-extension-sdk", "eval", {"policy_name": "p1"})
    assert res["policy_name"] == "p1"
    assert res["fail_closed"] is True


def test_b37_dependency_mapping_sdk(runtime):
    res = runtime.dispatch("b37-dependency-mapping-sdk", "map", {"source_coordinate": "dep.a"})
    assert res["source_coordinate"] == "dep.a"
    assert res["status"] == "MAPPED"


def test_b37_runner_job_sdk(runtime):
    res = runtime.dispatch("b37-runner-job-sdk", "load", {"job_type": "build"})
    assert res["lease_fencing_supported"] is True
    assert res["status"] == "SDK_LOADED"


def test_b37_vertical_pack_sdk(runtime):
    res = runtime.dispatch("b37-vertical-pack-sdk", "load", {"vertical": "fintech"})
    assert res["vertical"] == "fintech"
    assert "compliance_invariants" in res["components"]


def test_b37_sdk_compatibility_versioning(runtime):
    res = runtime.dispatch("b37-sdk-compatibility-versioning", "check", {"requested_version": "1.2.0"})
    assert res["is_compatible"] is True
    assert res["status"] == "COMPATIBLE"


def test_b37_publisher_onboarding_identity(runtime):
    res = runtime.dispatch("b37-publisher-onboarding-identity", "onboard", {"organization": "CorpLabs"})
    assert res["identity_verified"] is True
    assert res["status"] == "ONBOARDED"


def test_b37_publisher_lifecycle_key_rotation_offboarding(runtime):
    res = runtime.dispatch("b37-publisher-lifecycle-key-rotation-offboarding", "rotate", {"publisher_id": "p1"})
    assert res["key_version"] == "v2"
    assert res["status"] == "COMPLETED"


def test_b37_extension_manifest_abi_lifecycle(runtime):
    res = runtime.dispatch("b37-extension-manifest-abi-lifecycle", "validate", {"extension_id": "ext.test"})
    assert res["manifest_version"] == "1.0.0"
    assert res["lifecycle_state"] == "ACTIVE"


def test_b37_extension_local_development_toolkit(runtime):
    res = runtime.dispatch("b37-extension-local-development-toolkit", "exec", {"command": "test"})
    assert res["scaffolded"] is True
    assert res["status"] == "SUCCESS"


def test_b37_extension_signing_sbom_provenance(runtime):
    res = runtime.dispatch("b37-extension-signing-sbom-provenance", "verify", {"package_file": "ext.tar"})
    assert res["signature_valid"] is True
    assert res["slsa_level"] == 3


def test_b37_extension_sandbox_test_harness(runtime):
    res = runtime.dispatch("b37-extension-sandbox-test-harness", "test", {"extension_id": "ext.1"})
    assert res["filesystem_isolation"] is True
    assert res["status"] == "SANDBOX_PASSED"


def test_b37_extension_certification_security_review(runtime):
    res = runtime.dispatch("b37-extension-certification-security-review", "review", {"findings": []})
    assert res["critical_findings"] == 0
    assert res["certification_verdict"] == "APPROVED"


def test_b37_publish_install_upgrade_rollback_revoke(runtime):
    res = runtime.dispatch("b37-publish-install-upgrade-rollback-revoke", "install", {"action": "INSTALL", "extension": "ext.a"})
    assert res["action"] == "INSTALL"
    assert res["status"] == "INSTALL_SUCCESSFUL"


def test_b37_continuous_certification_recertification(runtime):
    res = runtime.dispatch("b37-continuous-certification-recertification", "recertify", {"extension_id": "ext.a"})
    assert res["recertified"] is True
    assert res["status"] == "CERTIFIED_CURRENT"


def test_b37_revocation_customer_continuity_replacement(runtime):
    res = runtime.dispatch("b37-revocation-customer-continuity-replacement", "revoke", {
        "revoked_extension": "ext.bad",
        "replacement_extension": "ext.good"
    })
    assert res["customer_notification_sent"] is True
    assert res["status"] == "REVOKED_WITH_REPLACEMENT"


def test_b37_extension_configuration_state_data_migration(runtime):
    res = runtime.dispatch("b37-extension-configuration-state-data-migration", "migrate", {
        "source_config": {"v1_key": "abc"}
    })
    assert res["migrated_config"]["v2_key"] == "abc"
    assert res["data_loss"] is False


def test_b37_extension_eol_data_portability_exit(runtime):
    res = runtime.dispatch("b37-extension-eol-data-portability-exit", "export", {"extension_id": "ext.old"})
    assert res["export_complete"] is True
    assert res["status"] == "PORTABILITY_EXPORTED"


def test_b37_marketplace_catalog_search_compatibility_discovery(runtime):
    res = runtime.dispatch("b37-marketplace-catalog-search-compatibility-discovery", "search", {"query": "spring"})
    assert res["total_matches"] >= 1
    assert res["status"] == "SEARCH_SUCCESS"


def test_b37_marketplace_ranking_review_abuse_governance(runtime):
    res = runtime.dispatch("b37-marketplace-ranking-review-abuse-governance", "audit", {"reviews": []})
    assert res["abuse_detected"] is False
    assert res["status"] == "GOVERNED"


def test_b37_enterprise_private_marketplace_allowlist_promotion(runtime):
    res = runtime.dispatch("b37-enterprise-private-marketplace-allowlist-promotion", "enforce", {
        "tenant_id": "t1", "allowlist": ["ext.a"]
    })
    assert res["allowlist_enforced"] is True
    assert res["status"] == "ALLOWLIST_ACTIVE"


def test_b37_airgapped_mirror_offline_revocation_license(runtime):
    res = runtime.dispatch("b37-airgapped-mirror-offline-revocation-license", "verify_mirror", {"bundle": "b.tar"})
    assert res["mirror_signed"] is True
    assert res["status"] == "AIRGAP_READY"


def test_b37_commercial_license_billing_revenue_share(runtime):
    res = runtime.dispatch("b37-commercial-license-billing-revenue-share", "calculate", {
        "gross_amount_usd": 100.0, "platform_share_pct": 0.20
    })
    assert res["platform_share_usd"] == 20.0
    assert res["publisher_share_usd"] == 80.0


def test_b37_commercial_settlement_refund_tax_fraud(runtime):
    res = runtime.dispatch("b37-commercial-settlement-refund-tax-fraud", "settle", {"period": "2026-Q1"})
    assert res["reconciliation_balanced"] is True
    assert res["fraud_flags"] == 0


def test_b37_marketplace_support_incident_dispute_sla(runtime):
    res = runtime.dispatch("b37-marketplace-support-incident-dispute-sla", "handle", {"dispute_id": "d1"})
    assert res["sla_tier"] == "TIER_1_4_HOUR"
    assert res["status"] == "ACKNOWLEDGED"


def test_b37_marketplace_legal_takedown_export_appeal(runtime):
    res = runtime.dispatch("b37-marketplace-legal-takedown-export-appeal", "takedown", {"notice_id": "n1"})
    assert res["action_taken"] == "TEMPORARY_QUARANTINE"
    assert res["status"] == "QUARANTINED"


def test_b37_marketplace_sre_incident_dr_operations(runtime):
    res = runtime.dispatch("b37-marketplace-sre-incident-dr-operations", "test_dr", {"dr_test": "failover"})
    assert res["failover_successful"] is True
    assert res["rto_seconds"] == 12


def test_b37_extension_dependency_lock_composition(runtime):
    res = runtime.dispatch("b37-extension-dependency-lock-composition", "lock", {"extensions": ["a", "b"]})
    assert res["extensions_composed"] == 2
    assert res["cycles_detected"] is False


def test_b37_extension_runtime_health_reconciliation(runtime):
    res = runtime.dispatch("b37-extension-runtime-health-reconciliation", "reconcile", {"instances": 3, "healthy_instances": 3})
    assert res["reconciliation_required"] is False
    assert res["status"] == "HEALTHY"


def test_b37_marketplace_certification_gate(runtime):
    res_pass = runtime.dispatch("b37-marketplace-certification-gate", "gate", {
        "evidence": {"security_passed": True, "sandbox_passed": True, "provenance_passed": True}
    })
    assert res_pass["gate_decision"] == "PASSED"
    assert res_pass["certification_status"] == "CERTIFIED"


def test_b37_marketplace_closure_certification_gate(runtime):
    res_pass = runtime.dispatch("b37-marketplace-closure-certification-gate", "gate", {
        "evidence": {"core_gate_passed": True, "commercial_settled": True, "sre_ready": True, "legal_cleared": True}
    })
    assert res_pass["closure_decision"] == "PASSED"
    assert res_pass["closure_certification_status"] == "CERTIFIED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b37-unknown", "op")
