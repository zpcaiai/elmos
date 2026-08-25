"""Strict allowlisted dispatcher for all fifty Project Intelligence Skills."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from .canonical import canonical_digest, canonical_value
from .domain import (
    CapabilityOutcome,
    analyze_impact,
    answer_project_query,
    apply_diagram_patch,
    authorize_and_audit,
    baseline_product_scope,
    bind_claim_evidence,
    build_debug_mission,
    build_intelligence_graph,
    build_replay_bundle,
    build_symbol_graph,
    build_threat_model,
    bundle_report,
    cache_analysis_stage,
    compile_diagram_spec,
    compile_onboarding_path,
    compile_reference_architecture,
    correlate_debug_events,
    derive_data_lineage,
    detect_architecture_drift,
    discover_architecture,
    discover_flows,
    estimate_runtime_cost,
    evaluate_architecture_rules,
    evaluate_entitlement_usage,
    evaluate_quality,
    evaluate_release_readiness,
    evaluate_slo,
    explain_from_evidence,
    fingerprint_revision,
    freeze_revision,
    fuse_runtime_observations,
    generate_document,
    generate_presentation,
    map_capabilities,
    navigate_graph,
    negotiate_debug_adapter,
    orchestrate_analysis,
    parse_revision,
    plan_debug_session,
    plan_deployment,
    plan_draft_pr,
    plan_repository_shards,
    read_revision_slice,
    reconcile_api_event_topology,
    reduce_debug_view,
    render_diagram,
    score_risk_and_debt,
    validate_connector_contract,
    validate_conversion_mapping,
    version_artifact,
)


class SkillRuntimeError(ValueError):
    """Raised for an unknown Skill or malformed strict request."""


CapabilityOperation = Callable[[Mapping[str, Any]], CapabilityOutcome]


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    schema_version: str
    request_id: str
    tenant_id: str
    project_id: str
    revision: str
    inputs: Mapping[str, Any]
    actor_id: str | None = None
    purpose: str | None = None

    @staticmethod
    def _identifier(value: Any, field_name: str) -> str:
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
            raise SkillRuntimeError(
                f"{field_name} must be a non-empty identifier of at most 256 bytes"
            )
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise SkillRuntimeError(f"{field_name} contains a control character")
        return value

    @classmethod
    def parse(cls, value: Mapping[str, Any]) -> "RuntimeRequest":
        if not isinstance(value, Mapping):
            raise SkillRuntimeError("request must be an object")
        allowed = {
            "schema_version",
            "request_id",
            "tenant_id",
            "project_id",
            "revision",
            "inputs",
            "actor_id",
            "purpose",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise SkillRuntimeError(f"request contains unsupported fields: {extra}")
        if value.get("schema_version") != "1.0":
            raise SkillRuntimeError("schema_version must be 1.0")
        inputs = value.get("inputs")
        if not isinstance(inputs, Mapping):
            raise SkillRuntimeError("inputs must be an object")
        actor = value.get("actor_id")
        purpose = value.get("purpose")
        return cls(
            schema_version="1.0",
            request_id=cls._identifier(value.get("request_id"), "request_id"),
            tenant_id=cls._identifier(value.get("tenant_id"), "tenant_id"),
            project_id=cls._identifier(value.get("project_id"), "project_id"),
            revision=cls._identifier(value.get("revision"), "revision"),
            inputs=canonical_value(dict(inputs)),
            actor_id=None if actor is None else cls._identifier(actor, "actor_id"),
            purpose=None if purpose is None else cls._identifier(purpose, "purpose"),
        )


@dataclass(frozen=True, slots=True)
class HandlerBinding:
    ordinal: int
    skill: str
    handler_id: str
    capability_state: str
    expected_success_code: str
    category: str
    operation: CapabilityOperation


_SPECS: Final[tuple[tuple[str, str, str, str, CapabilityOperation], ...]] = (
    (
        "elmos-insight-orchestrator",
        "LOCAL",
        "ANALYSIS_PLAN_COMPILED",
        "orchestration",
        orchestrate_analysis,
    ),
    (
        "elmos-product-scope",
        "LOCAL",
        "PRODUCT_SCOPE_BASELINED",
        "foundation",
        baseline_product_scope,
    ),
    (
        "elmos-reference-architecture",
        "LOCAL",
        "REFERENCE_ARCHITECTURE_COMPILED",
        "foundation",
        compile_reference_architecture,
    ),
    (
        "elmos-repository-ingestion",
        "PARTIAL",
        "LOCAL_REVISION_FROZEN",
        "ingestion",
        freeze_revision,
    ),
    (
        "elmos-project-fingerprinting",
        "LOCAL",
        "REVISION_FINGERPRINTED",
        "ingestion",
        fingerprint_revision,
    ),
    (
        "elmos-multilanguage-parsing",
        "PARTIAL",
        "BOUNDED_CODE_IR_PARSED",
        "analysis-core",
        parse_revision,
    ),
    (
        "elmos-symbol-code-graph",
        "PARTIAL",
        "SYMBOL_GRAPH_BUILT",
        "analysis-core",
        build_symbol_graph,
    ),
    (
        "elmos-project-intelligence-graph",
        "LOCAL",
        "INTELLIGENCE_GRAPH_SNAPSHOT_BUILT",
        "analysis-core",
        build_intelligence_graph,
    ),
    (
        "elmos-evidence-provenance",
        "LOCAL",
        "CLAIMS_BOUND_TO_EVIDENCE",
        "analysis-core",
        bind_claim_evidence,
    ),
    (
        "elmos-online-code-reader",
        "PARTIAL",
        "CODE_READER_SLICE_READY",
        "experience",
        read_revision_slice,
    ),
    (
        "elmos-semantic-navigation",
        "LOCAL",
        "SEMANTIC_NAVIGATION_RESOLVED",
        "experience",
        navigate_graph,
    ),
    (
        "elmos-code-explanation",
        "PARTIAL",
        "EVIDENCE_FACT_SHEET_GENERATED",
        "experience",
        explain_from_evidence,
    ),
    (
        "elmos-onboarding-learning-path",
        "LOCAL",
        "ONBOARDING_PATH_COMPILED",
        "experience",
        compile_onboarding_path,
    ),
    (
        "elmos-architecture-discovery",
        "LOCAL",
        "STATIC_ARCHITECTURE_DISCOVERED",
        "architecture",
        discover_architecture,
    ),
    (
        "elmos-business-capability-map",
        "PARTIAL",
        "CAPABILITY_CANDIDATES_MAPPED",
        "architecture",
        map_capabilities,
    ),
    (
        "elmos-flow-discovery",
        "PARTIAL",
        "STATIC_FLOW_CANDIDATES_DISCOVERED",
        "architecture",
        discover_flows,
    ),
    (
        "elmos-data-architecture-lineage",
        "PARTIAL",
        "STATIC_DATA_LINEAGE_DERIVED",
        "architecture",
        derive_data_lineage,
    ),
    (
        "elmos-api-event-topology",
        "PARTIAL",
        "DECLARED_API_EVENT_TOPOLOGY_RECONCILED",
        "architecture",
        reconcile_api_event_topology,
    ),
    (
        "elmos-runtime-trace-fusion",
        "PARTIAL",
        "SUPPLIED_RUNTIME_OBSERVATIONS_FUSED",
        "architecture",
        fuse_runtime_observations,
    ),
    (
        "elmos-diagram-spec-engine",
        "LOCAL",
        "DIAGRAM_SPEC_COMPILED",
        "artifacts",
        compile_diagram_spec,
    ),
    (
        "elmos-diagram-rendering",
        "PARTIAL",
        "SAFE_MERMAID_RENDERED",
        "artifacts",
        render_diagram,
    ),
    (
        "elmos-diagram-editor",
        "PARTIAL",
        "DIAGRAM_PATCH_APPLIED",
        "artifacts",
        apply_diagram_patch,
    ),
    (
        "elmos-architecture-documentation",
        "LOCAL",
        "ARCHITECTURE_DOCUMENT_GENERATED",
        "artifacts",
        generate_document,
    ),
    (
        "elmos-presentation-generation",
        "PARTIAL",
        "PRESENTATION_MANIFEST_GENERATED",
        "artifacts",
        generate_presentation,
    ),
    (
        "elmos-project-report-bundle",
        "LOCAL",
        "REPORT_BUNDLE_INDEXED",
        "artifacts",
        bundle_report,
    ),
    (
        "elmos-project-search-qa",
        "PARTIAL",
        "PROJECT_QUERY_ANSWERED",
        "intelligence",
        answer_project_query,
    ),
    (
        "elmos-impact-analysis",
        "LOCAL",
        "CHANGE_IMPACT_ANALYZED",
        "intelligence",
        analyze_impact,
    ),
    (
        "elmos-architecture-rules",
        "LOCAL",
        "ARCHITECTURE_RULES_EVALUATED",
        "intelligence",
        evaluate_architecture_rules,
    ),
    (
        "elmos-architecture-drift",
        "LOCAL",
        "ARCHITECTURE_DRIFT_DETECTED",
        "intelligence",
        detect_architecture_drift,
    ),
    (
        "elmos-risk-technical-debt",
        "LOCAL",
        "RISK_AND_TECHNICAL_DEBT_SCORED",
        "intelligence",
        score_risk_and_debt,
    ),
    (
        "elmos-security-threat-model",
        "PARTIAL",
        "BOUNDED_THREAT_MODEL_BUILT",
        "intelligence",
        build_threat_model,
    ),
    (
        "elmos-incremental-analysis-cache",
        "LOCAL",
        "ANALYSIS_CACHE_KEY_RESOLVED",
        "platform",
        cache_analysis_stage,
    ),
    (
        "elmos-artifact-versioning-human-lock",
        "LOCAL",
        "ARTIFACT_VERSION_CREATED",
        "platform",
        version_artifact,
    ),
    (
        "elmos-git-pr-automation",
        "PLAN",
        "DRAFT_PR_PLAN_VALIDATED",
        "platform",
        plan_draft_pr,
    ),
    (
        "elmos-collaboration-governance",
        "PARTIAL",
        "LOCAL_POLICY_ALLOWED",
        "enterprise",
        authorize_and_audit,
    ),
    (
        "elmos-integrations-mcp",
        "PLAN",
        "CONNECTOR_CONTRACT_VALIDATED",
        "enterprise",
        validate_connector_contract,
    ),
    (
        "elmos-large-repository-scaling",
        "PARTIAL",
        "REPOSITORY_SHARDS_PLANNED",
        "platform",
        plan_repository_shards,
    ),
    ("elmos-observability-slo", "LOCAL", "SLO_EVALUATED", "operations", evaluate_slo),
    (
        "elmos-testing-evaluation",
        "LOCAL",
        "LOCAL_QUALITY_EVALUATED",
        "quality",
        evaluate_quality,
    ),
    (
        "elmos-conversion-integration",
        "PARTIAL",
        "CONVERSION_MAPPING_VALIDATED",
        "integration",
        validate_conversion_mapping,
    ),
    (
        "elmos-runtime-cost-estimator",
        "LOCAL",
        "RUNTIME_COST_ESTIMATED",
        "operations",
        estimate_runtime_cost,
    ),
    (
        "elmos-deployment-private-cloud",
        "PLAN",
        "DEPLOYMENT_READINESS_PLANNED",
        "operations",
        plan_deployment,
    ),
    (
        "elmos-release-certification",
        "PLAN",
        "RELEASE_READINESS_EVALUATED",
        "quality",
        evaluate_release_readiness,
    ),
    (
        "elmos-commercial-packaging",
        "PARTIAL",
        "LOCAL_ENTITLEMENT_EVALUATED",
        "product",
        evaluate_entitlement_usage,
    ),
    (
        "elmos-debug-adapter-gateway",
        "PARTIAL",
        "DEBUG_CAPABILITIES_NEGOTIATED",
        "debug-platform",
        negotiate_debug_adapter,
    ),
    (
        "elmos-debug-sandbox-orchestration",
        "PLAN",
        "DEBUG_SANDBOX_SESSION_PLANNED",
        "debug-platform",
        plan_debug_session,
    ),
    (
        "elmos-online-debug-workbench",
        "PARTIAL",
        "DEBUG_VIEW_STATE_REDUCED",
        "debug-experience",
        reduce_debug_view,
    ),
    (
        "elmos-debug-learning-copilot",
        "PARTIAL",
        "DEBUG_LEARNING_MISSION_BUILT",
        "debug-learning",
        build_debug_mission,
    ),
    (
        "elmos-debug-record-replay",
        "PARTIAL",
        "R0_REPLAY_BUNDLE_BUILT",
        "debug-runtime",
        build_replay_bundle,
    ),
    (
        "elmos-distributed-debug-correlation",
        "PARTIAL",
        "DEBUG_EVENTS_CORRELATED",
        "debug-integration",
        correlate_debug_events,
    ),
)


def _build_registry() -> dict[str, HandlerBinding]:
    registry: dict[str, HandlerBinding] = {}
    for ordinal, (skill, state, code, category, operation) in enumerate(_SPECS):
        handler_id = operation.__name__
        registry[skill] = HandlerBinding(
            ordinal=ordinal,
            skill=skill,
            handler_id=handler_id,
            capability_state=state,
            expected_success_code=code,
            category=category,
            operation=operation,
        )
    return registry


SKILL_REGISTRY: Final[Mapping[str, HandlerBinding]] = MappingProxyType(
    _build_registry()
)


def validate_skill_registry(expected_names: Sequence[str] | None = None) -> None:
    bindings = list(SKILL_REGISTRY.values())
    if len(bindings) != 50:
        raise SkillRuntimeError(f"expected 50 exact bindings, found {len(bindings)}")
    if sorted(binding.ordinal for binding in bindings) != list(range(50)):
        raise SkillRuntimeError("binding ordinals are not the exact 0..49 sequence")
    if len({binding.handler_id for binding in bindings}) != 50:
        raise SkillRuntimeError("every Skill must have a unique capability handler")
    if len({id(binding.operation) for binding in bindings}) != 50:
        raise SkillRuntimeError("handler callables must be unique")
    counts = {
        state: sum(binding.capability_state == state for binding in bindings)
        for state in ("LOCAL", "PARTIAL", "PLAN")
    }
    if counts != {"LOCAL": 21, "PARTIAL": 24, "PLAN": 5}:
        raise SkillRuntimeError(f"unexpected capability-state counts: {counts}")
    if expected_names is not None and list(SKILL_REGISTRY) != list(expected_names):
        raise SkillRuntimeError(
            "runtime binding names/order differ from the pinned source catalog"
        )


def dispatch_skill(skill: str, value: Mapping[str, Any]) -> dict[str, Any]:
    binding = SKILL_REGISTRY.get(skill)
    if binding is None:
        raise SkillRuntimeError(f"unknown Project Intelligence Skill: {skill}")
    try:
        request = RuntimeRequest.parse(value)
        outcome = binding.operation(request.inputs)
    except (TypeError, ValueError, KeyError) as exc:
        return {
            "schema_version": "elmos.project-intelligence.result.v1",
            "skill": skill,
            "handler_id": binding.handler_id,
            "state": "BLOCKED",
            "code": "REQUEST_OR_CAPABILITY_CONTRACT_REJECTED",
            "outputs": {},
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "external_effects_performed": False,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    result = {
        "schema_version": "elmos.project-intelligence.result.v1",
        "skill": skill,
        "handler_id": binding.handler_id,
        "capability_state": binding.capability_state,
        "request_id": request.request_id,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "revision": request.revision,
        **outcome.to_dict(),
    }
    result["result_digest"] = canonical_digest(result)
    return result


def capability_manifest() -> dict[str, Any]:
    validate_skill_registry()
    return {
        "schema_version": "elmos.project-intelligence.capabilities.v1",
        "source_package": "elmos-project-intelligence-skills",
        "source_version": "1.1.0",
        "counts": {"skills": 50, "local": 21, "partial": 24, "plan": 5},
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "capabilities": [
            {
                "ordinal": binding.ordinal,
                "skill": binding.skill,
                "handler_id": binding.handler_id,
                "capability_state": binding.capability_state,
                "expected_success_code": binding.expected_success_code,
                "category": binding.category,
                "code_path": "engines/project-intelligence-engine/src/elmos_project_intelligence/domain.py",
                "registry_path": "engines/project-intelligence-engine/src/elmos_project_intelligence/runtime.py",
                "test_path": "engines/project-intelligence-engine/tests/test_runtime.py",
            }
            for binding in SKILL_REGISTRY.values()
        ],
    }


__all__ = [
    "HandlerBinding",
    "RuntimeRequest",
    "SKILL_REGISTRY",
    "SkillRuntimeError",
    "capability_manifest",
    "dispatch_skill",
    "validate_skill_registry",
]
