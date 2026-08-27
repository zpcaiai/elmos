"""Strict allowlisted runtime for the 55 legacy-web modernization Skills."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .catalog import PackageCatalog
from .canonical import canonical_digest
from .contracts import CapabilityResult, RuntimeRequest
from .operations import PROFILES, execute_profile


class RuntimeErrorContract(ValueError):
    pass


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CATALOG = PackageCatalog.load(REPOSITORY_ROOT)


@dataclass(frozen=True, slots=True)
class HandlerBinding:
    ordinal: int
    skill_id: str
    handler_id: str
    phase: str
    operation: Callable[[RuntimeRequest], CapabilityResult]


# These are intentionally separate named entrypoints.  Each exact source Skill
# is statically visible in the allowlist below and can be qualified independently.
def execute_00_modernization_orchestrator(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["00-modernization-orchestrator"])
def execute_01_job_contract_and_policy_resolver(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["01-job-contract-and-policy-resolver"])
def execute_02_reproducible_repository_snapshot(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["02-reproducible-repository-snapshot"])
def execute_03_checkpoint_resume_cancel(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["03-checkpoint-resume-cancel"])
def execute_04_wall_clock_eta_and_cost_model(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["04-wall-clock-eta-and-cost-model"])
def execute_05_tool_authority_and_sandbox(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["05-tool-authority-and-sandbox"])
def execute_10_build_and_module_topology(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["10-build-and-module-topology"])
def execute_11_framework_and_version_fingerprinting(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["11-framework-and-version-fingerprinting"])
def execute_12_runtime_deployment_topology(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["12-runtime-deployment-topology"])
def execute_13_route_ownership_and_conflict_analysis(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["13-route-ownership-and-conflict-analysis"])
def execute_14_environment_config_overlay_analysis(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["14-environment-config-overlay-analysis"])
def execute_15_dependency_compatibility_and_jakarta_readiness(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["15-dependency-compatibility-and-jakarta-readiness"])
def execute_20_struts1_lifecycle_recovery(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["20-struts1-lifecycle-recovery"])
def execute_21_struts2_interceptor_pipeline_recovery(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["21-struts2-interceptor-pipeline-recovery"])
def execute_22_servlet_container_semantics_recovery(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["22-servlet-container-semantics-recovery"])
def execute_23_jsp_taglib_and_view_semantics(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["23-jsp-taglib-and-view-semantics"])
def execute_24_request_binding_and_type_conversion(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["24-request-binding-and-type-conversion"])
def execute_25_navigation_dispatch_and_error_semantics(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["25-navigation-dispatch-and-error-semantics"])
def execute_26_session_state_and_scope_semantics(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["26-session-state-and-scope-semantics"])
def execute_27_security_authn_authz_csrf_semantics(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["27-security-authn-authz-csrf-semantics"])
def execute_28_transaction_and_side_effect_topology(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["28-transaction-and-side-effect-topology"])
def execute_29_concurrency_lifecycle_and_threadlocal(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["29-concurrency-lifecycle-and-threadlocal"])
def execute_30_repository_evidence_graph(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["30-repository-evidence-graph"])
def execute_31_legacy_web_semantic_ir(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["31-legacy-web-semantic-ir"])
def execute_32_behavioral_contract_and_sequence_mining(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["32-behavioral-contract-and-sequence-mining"])
def execute_33_unknown_semantics_ledger(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["33-unknown-semantics-ledger"])
def execute_34_semantic_risk_scoring(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["34-semantic-risk-scoring"])
def execute_40_preserve_first_migration_strategy(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["40-preserve-first-migration-strategy"])
def execute_41_springboot4_target_architecture(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["41-springboot4-target-architecture"])
def execute_42_multi_module_conversion_wave_planner(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["42-multi-module-conversion-wave-planner"])
def execute_43_compatibility_shim_synthesis(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["43-compatibility-shim-synthesis"])
def execute_44_packaging_view_and_container_decision(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["44-packaging-view-and-container-decision"])
def execute_45_cutover_strangler_and_dual_run_plan(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["45-cutover-strangler-and-dual-run-plan"])
def execute_50_deterministic_ast_and_config_rewrite(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["50-deterministic-ast-and-config-rewrite"])
def execute_51_struts1_to_springmvc_generator(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["51-struts1-to-springmvc-generator"])
def execute_52_struts2_to_springmvc_generator(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["52-struts2-to-springmvc-generator"])
def execute_53_servlet_to_springmvc_generator(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["53-servlet-to-springmvc-generator"])
def execute_54_jakarta_and_dependency_migration(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["54-jakarta-and-dependency-migration"])
def execute_55_spring_security_validation_transaction_generator(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["55-spring-security-validation-transaction-generator"])
def execute_56_jsp_preserve_or_modernize(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["56-jsp-preserve-or-modernize"])
def execute_57_source_map_change_provenance(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["57-source-map-change-provenance"])
def execute_58_idempotent_change_set_commit(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["58-idempotent-change-set-commit"])
def execute_60_static_semantic_coverage(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["60-static-semantic-coverage"])
def execute_61_test_and_scenario_generation(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["61-test-and-scenario-generation"])
def execute_62_differential_http_and_view_oracle(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["62-differential-http-and-view-oracle"])
def execute_63_session_db_and_side_effect_diff(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["63-session-db-and-side-effect-diff"])
def execute_64_security_equivalence_and_hardening(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["64-security-equivalence-and-hardening"])
def execute_65_concurrency_performance_and_fault_verification(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["65-concurrency-performance-and-fault-verification"])
def execute_66_observability_and_trace_correlation(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["66-observability-and-trace-correlation"])
def execute_70_mismatch_classification(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["70-mismatch-classification"])
def execute_71_bounded_semantic_auto_repair(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["71-bounded-semantic-auto-repair"])
def execute_72_impact_based_regression_selection(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["72-impact-based-regression-selection"])
def execute_73_production_cutover_rollback(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["73-production-cutover-rollback"])
def execute_74_evidence_bundle_and_e0_e5_certification(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["74-evidence-bundle-and-e0-e5-certification"])
def execute_75_golden_route_benchmark_and_learning_cache(request: RuntimeRequest) -> CapabilityResult: return execute_profile(request, PROFILES["75-golden-route-benchmark-and-learning-cache"])


_OPERATIONS: Mapping[str, Callable[[RuntimeRequest], CapabilityResult]] = MappingProxyType({
    "00-modernization-orchestrator": execute_00_modernization_orchestrator,
    "01-job-contract-and-policy-resolver": execute_01_job_contract_and_policy_resolver,
    "02-reproducible-repository-snapshot": execute_02_reproducible_repository_snapshot,
    "03-checkpoint-resume-cancel": execute_03_checkpoint_resume_cancel,
    "04-wall-clock-eta-and-cost-model": execute_04_wall_clock_eta_and_cost_model,
    "05-tool-authority-and-sandbox": execute_05_tool_authority_and_sandbox,
    "10-build-and-module-topology": execute_10_build_and_module_topology,
    "11-framework-and-version-fingerprinting": execute_11_framework_and_version_fingerprinting,
    "12-runtime-deployment-topology": execute_12_runtime_deployment_topology,
    "13-route-ownership-and-conflict-analysis": execute_13_route_ownership_and_conflict_analysis,
    "14-environment-config-overlay-analysis": execute_14_environment_config_overlay_analysis,
    "15-dependency-compatibility-and-jakarta-readiness": execute_15_dependency_compatibility_and_jakarta_readiness,
    "20-struts1-lifecycle-recovery": execute_20_struts1_lifecycle_recovery,
    "21-struts2-interceptor-pipeline-recovery": execute_21_struts2_interceptor_pipeline_recovery,
    "22-servlet-container-semantics-recovery": execute_22_servlet_container_semantics_recovery,
    "23-jsp-taglib-and-view-semantics": execute_23_jsp_taglib_and_view_semantics,
    "24-request-binding-and-type-conversion": execute_24_request_binding_and_type_conversion,
    "25-navigation-dispatch-and-error-semantics": execute_25_navigation_dispatch_and_error_semantics,
    "26-session-state-and-scope-semantics": execute_26_session_state_and_scope_semantics,
    "27-security-authn-authz-csrf-semantics": execute_27_security_authn_authz_csrf_semantics,
    "28-transaction-and-side-effect-topology": execute_28_transaction_and_side_effect_topology,
    "29-concurrency-lifecycle-and-threadlocal": execute_29_concurrency_lifecycle_and_threadlocal,
    "30-repository-evidence-graph": execute_30_repository_evidence_graph,
    "31-legacy-web-semantic-ir": execute_31_legacy_web_semantic_ir,
    "32-behavioral-contract-and-sequence-mining": execute_32_behavioral_contract_and_sequence_mining,
    "33-unknown-semantics-ledger": execute_33_unknown_semantics_ledger,
    "34-semantic-risk-scoring": execute_34_semantic_risk_scoring,
    "40-preserve-first-migration-strategy": execute_40_preserve_first_migration_strategy,
    "41-springboot4-target-architecture": execute_41_springboot4_target_architecture,
    "42-multi-module-conversion-wave-planner": execute_42_multi_module_conversion_wave_planner,
    "43-compatibility-shim-synthesis": execute_43_compatibility_shim_synthesis,
    "44-packaging-view-and-container-decision": execute_44_packaging_view_and_container_decision,
    "45-cutover-strangler-and-dual-run-plan": execute_45_cutover_strangler_and_dual_run_plan,
    "50-deterministic-ast-and-config-rewrite": execute_50_deterministic_ast_and_config_rewrite,
    "51-struts1-to-springmvc-generator": execute_51_struts1_to_springmvc_generator,
    "52-struts2-to-springmvc-generator": execute_52_struts2_to_springmvc_generator,
    "53-servlet-to-springmvc-generator": execute_53_servlet_to_springmvc_generator,
    "54-jakarta-and-dependency-migration": execute_54_jakarta_and_dependency_migration,
    "55-spring-security-validation-transaction-generator": execute_55_spring_security_validation_transaction_generator,
    "56-jsp-preserve-or-modernize": execute_56_jsp_preserve_or_modernize,
    "57-source-map-change-provenance": execute_57_source_map_change_provenance,
    "58-idempotent-change-set-commit": execute_58_idempotent_change_set_commit,
    "60-static-semantic-coverage": execute_60_static_semantic_coverage,
    "61-test-and-scenario-generation": execute_61_test_and_scenario_generation,
    "62-differential-http-and-view-oracle": execute_62_differential_http_and_view_oracle,
    "63-session-db-and-side-effect-diff": execute_63_session_db_and_side_effect_diff,
    "64-security-equivalence-and-hardening": execute_64_security_equivalence_and_hardening,
    "65-concurrency-performance-and-fault-verification": execute_65_concurrency_performance_and_fault_verification,
    "66-observability-and-trace-correlation": execute_66_observability_and_trace_correlation,
    "70-mismatch-classification": execute_70_mismatch_classification,
    "71-bounded-semantic-auto-repair": execute_71_bounded_semantic_auto_repair,
    "72-impact-based-regression-selection": execute_72_impact_based_regression_selection,
    "73-production-cutover-rollback": execute_73_production_cutover_rollback,
    "74-evidence-bundle-and-e0-e5-certification": execute_74_evidence_bundle_and_e0_e5_certification,
    "75-golden-route-benchmark-and-learning-cache": execute_75_golden_route_benchmark_and_learning_cache,
})


def _build_registry() -> Mapping[str, HandlerBinding]:
    if set(_OPERATIONS) != set(CATALOG.skill_ids) or set(PROFILES) != set(CATALOG.skill_ids):
        raise RuntimeErrorContract("runtime operations do not cover the pinned 55-Skill catalog")
    return MappingProxyType({
        spec.skill_id: HandlerBinding(
            ordinal=index,
            skill_id=spec.skill_id,
            handler_id="legacy-web-handler:" + spec.skill_id,
            phase=spec.phase,
            operation=_OPERATIONS[spec.skill_id],
        ) for index, spec in enumerate(CATALOG.skills)
    })


SKILL_REGISTRY = _build_registry()


def validate_skill_registry() -> None:
    if len(SKILL_REGISTRY) != 55:
        raise RuntimeErrorContract("expected exactly 55 registered Skills")
    if tuple(SKILL_REGISTRY) != CATALOG.skill_ids:
        raise RuntimeErrorContract("registry order differs from pinned catalog")
    if len({item.handler_id for item in SKILL_REGISTRY.values()}) != 55:
        raise RuntimeErrorContract("handler IDs are not unique")
    if len({item.operation for item in SKILL_REGISTRY.values()}) != 55:
        raise RuntimeErrorContract("exact Skill handlers are not unique")
    for skill_id, binding in SKILL_REGISTRY.items():
        if skill_id not in PROFILES or binding.phase != CATALOG.by_id[skill_id].phase:
            raise RuntimeErrorContract(f"registry metadata drift for {skill_id}")


def dispatch(request_value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate, authorize and invoke one exact local handler."""

    try:
        request = RuntimeRequest.from_dict(request_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeErrorContract(str(exc)) from exc
    binding = SKILL_REGISTRY.get(request.skill_id)
    if binding is None:
        raise RuntimeErrorContract("unknown legacy-web Skill")
    try:
        result = binding.operation(request)
    except Exception as exc:
        # Do not leak repository content or exception traces into the API.
        return {"requestId": request.request_id, "skillId": request.skill_id, "handlerId": binding.handler_id, "state": "BLOCKED", "code": "HANDLER_FAILED_CLOSED", "error": "handler failed closed", "detailCode": type(exc).__name__, "externalEvidence": "NOT_RUN", "certification": "NOT_CERTIFIED", "sideEffects": False}
    if result.handler_id != binding.handler_id:
        result = CapabilityResult(skill_id=result.skill_id, handler_id=binding.handler_id, state=result.state, code=result.code, artifacts=result.artifacts, warnings=result.warnings, unavailable=result.unavailable, external_evidence=result.external_evidence, certification=result.certification, side_effects=False)
    value = result.to_dict()
    value.update({"requestId": request.request_id, "tenantId": request.tenant_id, "projectId": request.project_id, "jobId": request.job_id, "inputDigest": canonical_digest(request.inputs)})
    return value


def capability_manifest() -> list[dict[str, Any]]:
    return [{"ordinal": item.ordinal, "skillId": item.skill_id, "handlerId": item.handler_id, "phase": item.phase, "code": PROFILES[item.skill_id].code, "state": PROFILES[item.skill_id].state, "artifactType": PROFILES[item.skill_id].artifact_type} for item in SKILL_REGISTRY.values()]
