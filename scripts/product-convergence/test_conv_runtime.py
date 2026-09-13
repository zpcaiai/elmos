"""Unit and contract tests for all 42 Product Convergence skills."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/product-convergence"))

from conv_skill_runtime import ConvSkillRuntime


@pytest.fixture
def runtime():
    return ConvSkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 42
    for s in runtime.SKILLS:
        assert s.startswith("conv-")


def test_conv_product_convergence_orchestrator(runtime):
    res = runtime.dispatch("conv-product-convergence-orchestrator", "orchestrate", {})
    assert res["status"] == "CONVERGED"
    assert res["ready"] is True


def test_conv_capability_package_metamodel(runtime):
    res = runtime.dispatch("conv-capability-package-metamodel", "validate", {})
    assert res["status"] == "METAMODEL_VALIDATED"
    assert "Pack" in res["entity_types"]


def test_conv_capability_dependency_graph(runtime):
    res = runtime.dispatch("conv-capability-dependency-graph", "resolve", {})
    assert res["status"] == "DEPENDENCY_GRAPH_RESOLVED"
    assert res["acyclic"] is True


def test_conv_global_project_lifecycle(runtime):
    res = runtime.dispatch("conv-global-project-lifecycle", "verify", {"phase": "P2_PRODUCTION_TAKEOVER"})
    assert res["status"] == "PHASE_VERIFIED"
    assert res["gate_passed"] is True


def test_conv_capability_registry_support_matrix(runtime):
    res = runtime.dispatch("conv-capability-registry-support-matrix", "check", {})
    assert res["status"] == "SUPPORT_MATRIX_CONFIRMED"
    assert "Go" in res["supported_languages"]


def test_conv_control_plane_modular_monolith(runtime):
    res = runtime.dispatch("conv-control-plane-modular-monolith", "check", {})
    assert res["status"] == "CONTROL_PLANE_HEALTHY"
    assert res["architecture"] == "MODULAR_MONOLITH"


def test_conv_core_extension_boundary(runtime):
    res = runtime.dispatch("conv-core-extension-boundary", "enforce", {})
    assert res["status"] == "BOUNDARY_ENFORCED"
    assert res["core_abi_locked"] is True


def test_conv_durable_workflow_runtime(runtime):
    res = runtime.dispatch("conv-durable-workflow-runtime", "run", {"workflow_id": "wf-1"})
    assert res["status"] == "WORKFLOW_EXECUTION_COMPLETED"
    assert res["durable_checkpoints"] == 5


def test_conv_unified_policy_engine(runtime):
    res = runtime.dispatch("conv-unified-policy-engine", "eval", {"rule_name": "test-rule"})
    assert res["status"] == "POLICY_EVALUATION_SUCCESS"
    assert res["evaluation_result"] == "ALLOW"


def test_conv_global_evidence_graph(runtime):
    res = runtime.dispatch("conv-global-evidence-graph", "seal", {})
    assert res["status"] == "EVIDENCE_GRAPH_SEALED"
    assert res["tamper_proof"] is True


def test_conv_deterministic_migration_engine_reference(runtime):
    res = runtime.dispatch("conv-deterministic-migration-engine-reference", "verify", {})
    assert res["status"] == "REFERENCE_ENGINE_VERIFIED"
    assert res["ast_fidelity"] == 1.0


def test_conv_java_spring_csharp_reference_route(runtime):
    res = runtime.dispatch("conv-java-spring-csharp-reference-route", "certify", {})
    assert res["status"] == "REFERENCE_ROUTE_CERTIFIED"
    assert res["pass_rate"] == 1.0


def test_conv_reference_route_acceptance_profile(runtime):
    res = runtime.dispatch("conv-reference-route-acceptance-profile", "accept", {})
    assert res["status"] == "PROFILE_SATISFIED"
    assert res["acceptance_status"] == "ACCEPTED"


def test_conv_validation_lab_evidence_store(runtime):
    res = runtime.dispatch("conv-validation-lab-evidence-store", "sync", {})
    assert res["status"] == "EVIDENCE_STORE_SYNCHRONIZED"
    assert res["checksums_verified"] is True


def test_conv_test_pyramid_real_system_classification(runtime):
    res = runtime.dispatch("conv-test-pyramid-real-system-classification", "classify", {})
    assert res["status"] == "PYRAMID_CLASSIFICATION_VALID"
    assert res["pyramid_layers"]["unit"] > 1000


def test_conv_verified_migrated_workload_metrics(runtime):
    res = runtime.dispatch("conv-verified-migrated-workload-metrics", "verify", {})
    assert res["status"] == "METRICS_VERIFIED"
    assert res["physical_loc"] == 40070


def test_conv_private_runner_reference_implementation(runtime):
    res = runtime.dispatch("conv-private-runner-reference-implementation", "check", {})
    assert res["status"] == "PRIVATE_RUNNER_ONLINE"
    assert res["egress_restricted"] is True


def test_conv_migration_design_studio(runtime):
    res = runtime.dispatch("conv-migration-design-studio", "launch", {})
    assert res["status"] == "STUDIO_CONFIGURED"
    assert "ast-diff" in res["supported_views"]


def test_conv_customer_handoff_operability(runtime):
    res = runtime.dispatch("conv-customer-handoff-operability", "handoff", {})
    assert res["status"] == "OPERABILITY_HANDOFF_ACCEPTED"
    assert res["runbook_complete"] is True


def test_conv_edition_commercial_package_simplification(runtime):
    res = runtime.dispatch("conv-edition-commercial-package-simplification", "simplify", {})
    assert res["status"] == "PACKAGING_SIMPLIFIED"
    assert "ENTERPRISE" in res["tiers"]


def test_conv_cross_batch_contract_normalization(runtime):
    res = runtime.dispatch("conv-cross-batch-contract-normalization", "normalize", {})
    assert res["status"] == "CONTRACTS_NORMALIZED"
    assert res["schema_drift_detected"] is False


def test_conv_duplicate_skill_consolidation(runtime):
    res = runtime.dispatch("conv-duplicate-skill-consolidation", "consolidate", {})
    assert res["status"] == "SKILLS_CONSOLIDATED"
    assert res["canonical_mappings_enforced"] is True


def test_conv_skill_layering_routing(runtime):
    res = runtime.dispatch("conv-skill-layering-routing", "route", {})
    assert res["status"] == "ROUTING_LAYERED"
    assert res["dispatch_deterministic"] is True


def test_conv_pack_lifecycle_certification_unifier(runtime):
    res = runtime.dispatch("conv-pack-lifecycle-certification-unifier", "unify", {})
    assert res["status"] == "LIFECYCLE_UNIFIED"
    assert len(res["unified_gate_criteria"]) == 4


def test_conv_maintainability_gate(runtime):
    res = runtime.dispatch("conv-maintainability-gate", "evaluate", {"complexity": 8.0, "coverage": 0.90})
    assert res["status"] == "GATE_PASSED"
    assert res["passed"] is True

    res_fail = runtime.dispatch("conv-maintainability-gate", "evaluate", {"complexity": 25.0, "coverage": 0.60})
    assert res_fail["status"] == "GATE_REJECTED"
    assert res_fail["passed"] is False


def test_conv_design_partner_pilot(runtime):
    res = runtime.dispatch("conv-design-partner-pilot", "track", {})
    assert res["status"] == "PILOT_VERIFIED"
    assert res["partners_enrolled"] == 4


def test_conv_benchmark_corpus_governance(runtime):
    res = runtime.dispatch("conv-benchmark-corpus-governance", "govern", {})
    assert res["status"] == "BENCHMARK_GOVERNED"
    assert res["benchmarks_frozen"] is True


def test_conv_architecture_decision_change_control(runtime):
    res = runtime.dispatch("conv-architecture-decision-change-control", "commit", {"adr_id": "ADR-01"})
    assert res["status"] == "ADR_COMMITTED"
    assert res["approved_by_arch_board"] is True


def test_conv_product_information_architecture(runtime):
    res = runtime.dispatch("conv-product-information-architecture", "validate", {})
    assert res["status"] == "IA_STRUCTURE_VALID"
    assert res["broken_links_count"] == 0


def test_conv_skill_registry_compiler(runtime):
    res = runtime.dispatch("conv-skill-registry-compiler", "compile", {})
    assert res["status"] == "REGISTRY_COMPILED"
    assert res["skills_compiled"] == 42


def test_conv_cross_batch_integration_anti_fragmentation(runtime):
    res = runtime.dispatch("conv-cross-batch-integration-anti-fragmentation", "check", {})
    assert res["status"] == "ANTI_FRAGMENTATION_VERIFIED"
    assert res["cyclic_dependencies"] == 0


def test_conv_product_convergence_readiness_gate(runtime):
    res = runtime.dispatch("conv-product-convergence-readiness-gate", "evaluate", {"kernels_pass": True, "routes_pass": True})
    assert res["status"] == "GATE_PASSED"
    assert res["passed"] is True

    res_fail = runtime.dispatch("conv-product-convergence-readiness-gate", "evaluate", {"kernels_pass": False, "routes_pass": True})
    assert res_fail["status"] == "GATE_REJECTED"
    assert res_fail["passed"] is False


def test_conv_convergence_observability_debt_dashboard(runtime):
    res = runtime.dispatch("conv-convergence-observability-debt-dashboard", "report", {})
    assert res["status"] == "DEBT_DASHBOARD_HEALTHY"
    assert res["architecture_violations"] == 0


def test_conv_convergence_roadmap_p0_p3(runtime):
    res = runtime.dispatch("conv-convergence-roadmap-p0-p3", "check", {})
    assert res["status"] == "ROADMAP_ON_TRACK"
    assert len(res["roadmap_phases"]) == 4


def test_conv_customer_success_sla_operations_proof(runtime):
    res = runtime.dispatch("conv-customer-success-sla-operations-proof", "audit", {})
    assert res["status"] == "SLA_OPERATIONS_PROVEN"
    assert res["unresolved_breaches"] == 0


def test_conv_integration_contract_anti_corruption_layer(runtime):
    res = runtime.dispatch("conv-integration-contract-anti-corruption-layer", "check", {})
    assert res["status"] == "ACL_IN_EFFECT"
    assert res["acl_active"] is True


def test_conv_recipe_promotion_knowledge_governance(runtime):
    res = runtime.dispatch("conv-recipe-promotion-knowledge-governance", "govern", {})
    assert res["status"] == "RECIPES_GOVERNED"
    assert res["regression_safety_checked"] is True


def test_conv_reference_architecture_blueprint(runtime):
    res = runtime.dispatch("conv-reference-architecture-blueprint", "verify", {})
    assert res["status"] == "BLUEPRINT_APPROVED"
    assert "HA_MULTITENANT" in res["validated_topologies"]


def test_conv_reference_implementation_release_train(runtime):
    res = runtime.dispatch("conv-reference-implementation-release-train", "schedule", {})
    assert res["status"] == "RELEASE_TRAIN_SCHEDULED"
    assert res["ready_for_departure"] is True


def test_conv_reference_product_acceptance_review(runtime):
    res = runtime.dispatch("conv-reference-product-acceptance-review", "review", {})
    assert res["status"] == "ACCEPTANCE_REVIEW_PASSED"
    assert res["board_signoff"] is True


def test_conv_reference_repository_design_partner_corpus(runtime):
    res = runtime.dispatch("conv-reference-repository-design-partner-corpus", "stage", {})
    assert res["status"] == "CORPUS_STAGED"
    assert res["corpus_repos_count"] == 15


def test_conv_repeatable_profitable_delivery_model(runtime):
    res = runtime.dispatch("conv-repeatable-profitable-delivery-model", "evaluate", {})
    assert res["status"] == "DELIVERY_MODEL_VALIDATED"
    assert res["gross_margin"] >= 0.70


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("conv-non-existent-skill", "check")
