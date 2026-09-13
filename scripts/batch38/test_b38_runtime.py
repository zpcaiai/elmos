"""Test suite verifying all 22 Batch 38 Deployment & Upgrade skills in B38SkillRuntime."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from scripts.batch38.b38_skill_runtime import B38SkillRuntime


@pytest.fixture
def runtime():
    return B38SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 22
    for s in runtime.SKILLS:
        assert s.startswith("b38-")


def test_b38_enterprise_deployment_upgrade_factory(runtime):
    res = runtime.dispatch("b38-enterprise-deployment-upgrade-factory", "init", {"factory_id": "fac-demo"})
    assert res["factory_id"] == "fac-demo"
    assert "air-gapped" in res["supported_editions"]
    assert res["status"] == "INITIALIZED"
    assert res["ready"] is True


def test_b38_edition_responsibility_matrix(runtime):
    res = runtime.dispatch("b38-edition-responsibility-matrix", "query", {"edition": "air-gapped"})
    assert res["edition"] == "air-gapped"
    assert res["responsibility"]["compute"] == "Air-Gapped-Metal"
    assert res["status"] == "MATRIX_RESOLVED"


def test_b38_plane_topology_governance(runtime):
    res = runtime.dispatch("b38-plane-topology-governance", "govern", {})
    assert res["network_isolation_policy"] == "STRICT_EGRESS_DENY_DEFAULT"
    assert res["status"] == "TOPOLOGY_GOVERNED"


def test_b38_portable_control_plane(runtime):
    res = runtime.dispatch("b38-portable-control-plane", "bootstrap", {"storage_engine": "sqlite-embedded"})
    assert res["crd_operator_mode"] is True
    assert res["offline_bootstrap_capable"] is True
    assert res["status"] == "CONTROL_PLANE_READY"


def test_b38_self_hosted_edition(runtime):
    res = runtime.dispatch("b38-self-hosted-edition", "configure", {"license_key": "LIC-TEST-001"})
    assert res["license_key"] == "LIC-TEST-001"
    assert res["telemetry_mode"] == "OPT_OUT_AIRGAP"
    assert res["status"] == "SELF_HOSTED_CONFIGURED"


def test_b38_dedicated_saas_edition(runtime):
    res = runtime.dispatch("b38-dedicated-saas-edition", "provision", {"tenant_id": "t-dedi-9"})
    assert res["tenant_id"] == "t-dedi-9"
    assert "t-dedi-9" in res["dedicated_database"]
    assert res["status"] == "DEDICATED_PROVISIONED"


def test_b38_multitenant_saas_edition(runtime):
    res = runtime.dispatch("b38-multitenant-saas-edition", "provision", {"tenant_id": "t-multi-1"})
    assert res["noisy_neighbor_protection"] is True
    assert "ROW_LEVEL_SECURITY" in res["isolation_mechanism"]
    assert res["status"] == "TENANT_PROVISIONED"


def test_b38_customer_vpc_edition(runtime):
    res = runtime.dispatch("b38-customer-vpc-edition", "attach", {"vpc_id": "vpc-010101"})
    assert res["customer_vpc_id"] == "vpc-010101"
    assert res["egress_lockdown"] is True
    assert res["status"] == "VPC_ATTACHED"


def test_b38_private_sovereign_cloud_edition(runtime):
    res = runtime.dispatch("b38-private-sovereign-cloud-edition", "bind", {"jurisdiction": "EU-FR"})
    assert res["jurisdiction"] == "EU-FR"
    assert res["cross_border_egress_blocked"] is True
    assert res["status"] == "SOVEREIGN_BOUND"


def test_b38_air_gapped_edition(runtime):
    res = runtime.dispatch("b38-air-gapped-edition", "verify", {"media_digest": "sha256:abc123"})
    assert res["air_gapped"] is True
    assert res["internet_access_verified"] is False
    assert res["status"] == "AIR_GAPPED_VERIFIED"


def test_b38_edge_plant_restricted_edition(runtime):
    res = runtime.dispatch("b38-edge-plant-restricted-edition", "bind", {"plant_id": "PLANT-02"})
    assert res["plant_id"] == "PLANT-02"
    assert res["local_buffer_hours"] == 72
    assert res["status"] == "EDGE_BOUND"


def test_b38_multiregion_active_active_edition(runtime):
    res = runtime.dispatch("b38-multiregion-active-active-edition", "establish", {})
    assert len(res["active_regions"]) >= 2
    assert res["rto_seconds"] <= 0.01
    assert res["rpo_seconds"] == 0.0
    assert res["status"] == "ACTIVE_ACTIVE_ESTABLISHED"


def test_b38_tenant_edition_migration(runtime):
    res = runtime.dispatch("b38-tenant-edition-migration", "plan", {"tenant_id": "t-100", "source_edition": "multitenant-saas", "target_edition": "dedicated-saas"})
    assert res["tenant_id"] == "t-100"
    assert len(res["migration_pipeline"]) >= 5
    assert res["data_loss"] == 0
    assert res["status"] == "MIGRATION_PLANNED"


def test_b38_platform_version_compatibility(runtime):
    res = runtime.dispatch("b38-platform-version-compatibility", "check", {"current_version": "2.0.0", "target_version": "2.1.0"})
    assert res["schema_backward_compatible"] is True
    assert res["abi_compatible"] is True
    assert res["status"] == "COMPATIBILITY_VERIFIED"


def test_b38_runner_version_compatibility(runtime):
    res = runtime.dispatch("b38-runner-version-compatibility", "check", {"runner_version": "2.5.0"})
    assert res["compatible"] is True
    assert res["status"] == "RUNNER_COMPATIBLE"


def test_b38_recipe_pack_extension_upgrade(runtime):
    res = runtime.dispatch("b38-recipe-pack-extension-upgrade", "upgrade", {"pack_name": "pack-1", "new_version": "3.0.0"})
    assert res["schema_evolution_safe"] is True
    assert res["rollback_snapshot_created"] is True
    assert res["status"] == "PACK_UPGRADED"


def test_b38_database_expand_contract_upgrade(runtime):
    res_expand = runtime.dispatch("b38-database-expand-contract-upgrade", "step", {"phase": "expand"})
    assert res_expand["dual_write_triggers_installed"] is True
    assert res_expand["status"] == "PHASE_EXPAND_COMPLETED"

    res_contract = runtime.dispatch("b38-database-expand-contract-upgrade", "step", {"phase": "contract"})
    assert res_contract["old_columns_dropped"] is True
    assert res_contract["status"] == "PHASE_CONTRACT_COMPLETED"


def test_b38_workflow_version_long_run_recovery(runtime):
    res = runtime.dispatch("b38-workflow-version-long-run-recovery", "recover", {"workflow_id": "wf-123"})
    assert res["checkpoint_restored"] is True
    assert res["status"] == "WORKFLOW_RECOVERED"


def test_b38_zero_downtime_upgrade(runtime):
    res = runtime.dispatch("b38-zero-downtime-upgrade", "execute", {"service_name": "billing-api"})
    assert res["dropped_connections"] == 0
    assert res["health_check_pass_rate"] == 1.0
    assert res["status"] == "ZERO_DOWNTIME_COMPLETE"


def test_b38_upgrade_rollback_disaster_recovery(runtime):
    res = runtime.dispatch("b38-upgrade-rollback-disaster-recovery", "prepare", {"rollback_target": "v1.0.0"})
    assert res["rollback_plan_validated"] is True
    assert res["status"] == "ROLLBACK_PREPARED"


def test_b38_offline_signed_update_bundle(runtime):
    res = runtime.dispatch("b38-offline-signed-update-bundle", "verify", {"bundle_id": "b-2026"})
    assert res["signature_valid"] is True
    assert res["tamper_evidence_detected"] is False
    assert res["status"] == "BUNDLE_VERIFIED"


def test_b38_deployment_upgrade_gate(runtime):
    res_pass = runtime.dispatch("b38-deployment-upgrade-gate", "eval", {"editionConformanceRate": 1.0, "upgradeRollbackPassRate": 1.0, "recoveryPassRate": 1.0})
    assert res_pass["passed"] is True
    assert res_pass["gate_decision"] == "PASS"

    res_fail = runtime.dispatch("b38-deployment-upgrade-gate", "eval", {"editionConformanceRate": 0.9, "upgradeRollbackPassRate": 1.0, "recoveryPassRate": 1.0})
    assert res_fail["passed"] is False
    assert res_fail["gate_decision"] == "BLOCKED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b38-nonexistent-skill", "init")
