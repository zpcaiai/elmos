"""Unit and contract tests for all 20 Batch 43 Product Lifecycle & Compatibility skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/batch43"))

from b43_skill_runtime import B43SkillRuntime


@pytest.fixture
def runtime():
    return B43SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 20
    for s in runtime.SKILLS:
        assert s.startswith("b43-")


def test_b43_product_lifecycle_factory(runtime):
    res = runtime.dispatch("b43-product-lifecycle-factory", "init", {})
    assert res["status"] == "LIFECYCLE_FACTORY_INITIALIZED"
    assert res["ready"] is True
    assert "LTS_SUPPORT" in res["governed_stages"]


def test_b43_version_specification(runtime):
    res = runtime.dispatch("b43-version-specification", "specify", {"version": "3.2.0"})
    assert res["status"] == "VERSION_SPECIFIED"
    assert res["semver_compliant"] is True


def test_b43_public_api_compatibility(runtime):
    res = runtime.dispatch("b43-public-api-compatibility", "check", {"breaking_changes": 0})
    assert res["status"] == "API_COMPATIBLE"
    assert res["backward_compatible"] is True

    res_fail = runtime.dispatch("b43-public-api-compatibility", "check", {"breaking_changes": 1})
    assert res_fail["status"] == "API_BREAKING_BLOCKED"


def test_b43_event_schema_compatibility(runtime):
    res = runtime.dispatch("b43-event-schema-compatibility", "validate", {})
    assert res["status"] == "EVENT_SCHEMA_COMPATIBLE"
    assert res["schema_evolution_valid"] is True


def test_b43_database_migration_compatibility(runtime):
    res = runtime.dispatch("b43-database-migration-compatibility", "validate", {})
    assert res["status"] == "DB_MIGRATION_COMPATIBLE"
    assert res["expand_contract_tested"] is True


def test_b43_psp_uir_schema_compatibility(runtime):
    res = runtime.dispatch("b43-psp-uir-schema-compatibility", "validate", {})
    assert res["status"] == "UIR_SCHEMA_COMPATIBLE"
    assert res["lossless_serialization_verified"] is True


def test_b43_runner_protocol_compatibility(runtime):
    res = runtime.dispatch("b43-runner-protocol-compatibility", "handshake", {})
    assert res["status"] == "RUNNER_PROTOCOL_COMPATIBLE"
    assert res["wire_compatible"] is True


def test_b43_sdk_compatibility(runtime):
    res = runtime.dispatch("b43-sdk-compatibility", "verify", {"language": "typescript"})
    assert res["status"] == "SDK_COMPATIBLE"
    assert res["abi_stable"] is True


def test_b43_recipe_pack_extension_compatibility(runtime):
    res = runtime.dispatch("b43-recipe-pack-extension-compatibility", "check", {})
    assert res["status"] == "RECIPE_EXTENSION_COMPATIBLE"
    assert res["ast_transform_engine_compatible"] is True


def test_b43_compatibility_test_matrix(runtime):
    res = runtime.dispatch("b43-compatibility-test-matrix", "run_matrix", {"matrix_failures": 0})
    assert res["status"] == "MATRIX_TESTS_PASSED"
    assert res["pass_rate"] == 1.0

    res_fail = runtime.dispatch("b43-compatibility-test-matrix", "run_matrix", {"matrix_failures": 2, "cells_count": 50})
    assert res_fail["status"] == "MATRIX_TESTS_FAILED"


def test_b43_rolling_mixed_version_upgrade(runtime):
    res = runtime.dispatch("b43-rolling-mixed-version-upgrade", "simulate", {})
    assert res["status"] == "MIXED_VERSION_ROLLING_SUCCESSFUL"
    assert res["zero_request_drop"] is True


def test_b43_deprecation_removal(runtime):
    res = runtime.dispatch("b43-deprecation-removal", "evaluate", {})
    assert res["status"] == "DEPRECATION_POLICY_SATISFIED"
    assert res["safe_to_remove"] is True


def test_b43_automated_upgrade_tooling(runtime):
    res = runtime.dispatch("b43-automated-upgrade-tooling", "validate", {})
    assert res["status"] == "UPGRADE_TOOLING_VERIFIED"
    assert res["automatic_manifest_rewrite"] is True


def test_b43_feature_flag_progressive_enable(runtime):
    res = runtime.dispatch("b43-feature-flag-progressive-enable", "rollout", {"percentage": 50})
    assert res["status"] == "FLAG_PROGRESSIVELY_ENABLED"
    assert res["killswitch_available"] is True


def test_b43_customer_upgrade_readiness(runtime):
    res = runtime.dispatch("b43-customer-upgrade-readiness", "assess", {})
    assert res["status"] == "CUSTOMER_UPGRADE_READY"
    assert res["readiness_score"] == 1.0


def test_b43_release_channel_governance(runtime):
    res = runtime.dispatch("b43-release-channel-governance", "govern", {"channel": "stable"})
    assert res["status"] == "RELEASE_CHANNEL_GOVERNED"
    assert res["minimum_soak_time_days"] == 7


def test_b43_release_documentation(runtime):
    res = runtime.dispatch("b43-release-documentation", "publish", {"version": "v3.2.0"})
    assert res["status"] == "RELEASE_DOCS_PUBLISHED"
    assert res["security_advisories_included"] is True


def test_b43_security_fix_backport(runtime):
    res = runtime.dispatch("b43-security-fix-backport", "backport", {"cve_id": "CVE-01"})
    assert res["status"] == "SECURITY_FIX_BACKPORTED"
    assert res["all_tests_green"] is True


def test_b43_support_eol_policy(runtime):
    res = runtime.dispatch("b43-support-eol-policy", "policy", {})
    assert res["status"] == "EOL_POLICY_PUBLISHED"
    assert res["migration_assistance_sla_active"] is True


def test_b43_product_lifecycle_gate(runtime):
    res = runtime.dispatch("b43-product-lifecycle-gate", "evaluate", {
        "compatibilityMatrixPassRate": 1.0,
        "upgradePassRate": 1.0,
        "unsupportedBreakingChangeCount": 0.0,
    })
    assert res["passed"] is True
    assert res["status"] == "GATE_PASSED"

    res_fail = runtime.dispatch("b43-product-lifecycle-gate", "evaluate", {
        "compatibilityMatrixPassRate": 0.95,
        "upgradePassRate": 1.0,
        "unsupportedBreakingChangeCount": 1.0,
    })
    assert res_fail["passed"] is False
    assert res_fail["status"] == "GATE_REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b43-non-existent-skill", "check")
