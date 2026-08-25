"""Allowlisted runtime bindings for all forty autonomous QA Skills.

Every installed Skill resolves to one exact repository-owned callable.  Source
documents, workflow action strings, SQL, replay scripts, and prompt text are
never dispatched.  Handlers implement deterministic local semantics and keep
effects requiring an isolated runner, SCM, publisher, signer, or independent
verifier explicitly outside this boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from . import (
    adapters,
    advanced_skills,
    context_skills,
    delivery_service,
    delivery_skills,
    domain,
    gates,
    generators,
    trusted_services,
)
from .contracts import (
    ContractError,
    HandlerOutputError,
    RuntimeRequest,
    digest_json,
    normalize_result,
    strict_json,
)


class SkillRuntimeError(ValueError):
    """Raised when the caller selects an unknown or malformed Skill."""


SkillOperation = Callable[[Mapping[str, Any]], Mapping[str, Any]]
SkillHandler = Callable[[RuntimeRequest], Mapping[str, Any]]


@dataclass(frozen=True)
class HandlerBinding:
    ordinal: int
    source_id: str
    skill: str
    handler_id: str
    phase: str
    mutating: bool
    operation_id: str
    handler: SkillHandler


PHASE_DAG: Final[Mapping[str, tuple[str, ...]]] = {
    "control": ("context",),
    "context": ("planning",),
    "planning": ("generation", "delivery-plan"),
    "generation": ("materialization",),
    "materialization": ("execution",),
    "execution": ("evidence",),
    "evidence": ("repair", "gate"),
    "repair": ("gate",),
    "gate": ("reporting",),
    "reporting": ("publishing",),
    "delivery-plan": ("materialization",),
    "publishing": ("lifecycle",),
    "lifecycle": (),
}


def _external_plan(operation: SkillOperation) -> SkillOperation:
    def invoke(inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        result = dict(operation(inputs))
        # A local validation blocker remains local evidence.  Only a successful
        # plan that is ready for an external side effect is labelled as needing
        # an adapter; otherwise this wrapper would conceal the actual failure.
        if "implementation_state" not in result:
            result["implementation_state"] = "EXTERNAL_ADAPTER_REQUIRED"
        elif str(result.get("state", "")).upper() == "SUCCEEDED":
            result["implementation_state"] = "EXTERNAL_ADAPTER_REQUIRED"
        return result

    invoke.__qa_operation_id__ = (  # type: ignore[attr-defined]
        f"external-plan:{operation.__module__}.{operation.__qualname__}"
    )
    return invoke


def _make_handler(
    source_id: str,
    operation: SkillOperation,
    *,
    mutating: bool,
) -> SkillHandler:
    def handler(request: RuntimeRequest) -> Mapping[str, Any]:
        if request.policy or request.capabilities:
            raise ContractError(
                "policy and capability envelopes require a trusted repository binder"
            )
        if mutating:
            if request.actor_id is None:
                raise ContractError("actor_id is required for a mutating Skill")
            if request.idempotency_key is None:
                raise ContractError("idempotency_key is required for a mutating Skill")
        if "_runtime_context" in request.inputs:
            raise ContractError("inputs._runtime_context is runtime-owned")
        operation_inputs = dict(request.inputs)
        operation_inputs["_runtime_context"] = {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "actor_id": request.actor_id,
            "request_id": request.request_id,
            "idempotency_key": request.idempotency_key,
        }
        result = dict(operation(operation_inputs))
        return result

    handler.__name__ = "execute_" + source_id.replace("-", "_")
    handler.__qualname__ = handler.__name__
    return handler


def _operation_identity(operation: SkillOperation) -> str:
    declared = getattr(operation, "__qa_operation_id__", None)
    if isinstance(declared, str) and declared:
        return declared
    return f"{operation.__module__}.{operation.__qualname__}"


_SPECS: Final[tuple[tuple[str, str, bool, SkillOperation], ...]] = (
    ("00-qa-control-plane", "control", True, trusted_services.control_plane_operation_contract),
    ("01-project-context-ingestion", "context", False, trusted_services.project_context_operation_contract),
    ("02-spec-normalization", "context", False, context_skills.normalize_specification),
    ("03-requirement-traceability-graph", "planning", False, context_skills.build_traceability_graph),
    ("04-risk-coverage-planning", "planning", False, context_skills.plan_risk_coverage),
    ("05-test-model-dsl", "generation", False, context_skills.compile_test_model),
    (
        "06-functional-test-generation",
        "generation",
        False,
        generators.generate_functional_tests,
    ),
    (
        "07-api-contract-testing",
        "generation",
        False,
        generators.plan_api_contract_tests,
    ),
    (
        "08-data-database-testing",
        "generation",
        False,
        generators.plan_database_tests,
    ),
    (
        "09-message-workflow-testing",
        "generation",
        False,
        generators.plan_message_workflow_tests,
    ),
    (
        "10-ui-e2e-testing",
        "generation",
        False,
        generators.plan_ui_e2e_tests,
    ),
    (
        "11-visual-responsive-testing",
        "generation",
        False,
        generators.plan_visual_responsive_tests,
    ),
    (
        "12-accessibility-compatibility-testing",
        "generation",
        False,
        generators.plan_accessibility_compatibility_tests,
    ),
    (
        "13-performance-baseline-testing",
        "generation",
        False,
        generators.plan_performance_baseline_tests,
    ),
    (
        "14-load-stress-spike-soak-testing",
        "generation",
        False,
        generators.plan_load_stress_spike_soak_tests,
    ),
    (
        "15-security-abuse-testing",
        "generation",
        False,
        generators.plan_security_abuse_tests,
    ),
    (
        "16-resilience-chaos-recovery-testing",
        "generation",
        False,
        generators.plan_resilience_chaos_recovery_tests,
    ),
    ("17-test-data-management", "execution", False, context_skills.prepare_test_data),
    ("18-environment-orchestration", "execution", False, context_skills.plan_environment_orchestration),
    ("19-distributed-test-execution", "execution", False, advanced_skills.plan_shards),
    ("20-test-oracle-evidence", "evidence", False, advanced_skills.verify_evidence),
    ("21-flaky-test-control", "evidence", False, advanced_skills.classify_flaky),
    ("22-defect-triage-rca", "repair", False, advanced_skills.triage_defects),
    ("23-repair-planning", "repair", False, advanced_skills.plan_repair),
    ("24-safe-code-auto-fix", "repair", True, _external_plan(domain.validate_patch)),
    ("25-test-self-healing", "repair", True, _external_plan(domain.validate_test_heal)),
    ("26-impact-analysis-regression", "repair", False, advanced_skills.analyze_impact),
    ("27-mutation-property-fuzz-testing", "generation", False, advanced_skills.plan_advanced_testing),
    (
        "28-quality-gate-release-certification",
        "gate",
        False,
        gates.evaluate_quality_gate_contract,
    ),
    ("29-reporting-observability", "reporting", False, advanced_skills.build_report),
    ("30-checkpoint-resume-idempotency", "control", True, advanced_skills.create_checkpoint),
    ("31-runtime-cost-eta", "planning", False, advanced_skills.estimate_eta),
    (
        "32-multilanguage-adapter-sdk",
        "generation",
        False,
        adapters.execute_adapter_contract,
    ),
    ("33-ci-cd-pr-integration", "publishing", True, _external_plan(domain.plan_ci)),
    ("34-continuous-learning-knowledge-base", "lifecycle", True, advanced_skills.propose_learning),
    ("35-governance-approval-audit", "control", False, advanced_skills.authorize_action),
    ("36-project-output-contract", "delivery-plan", False, delivery_skills.plan_project_output_contract),
    ("37-test-source-materialization", "materialization", True, delivery_skills.emit_test_sources),
    (
        "38-project-output-bundle-publishing",
        "publishing",
        True,
        delivery_service.publishing_operation_contract,
    ),
    (
        "39-output-versioning-retention",
        "lifecycle",
        True,
        delivery_service.lifecycle_operation_contract,
    ),
)

CANONICAL_BINDING_CONTRACT: Final[tuple[tuple[str, str, bool, str], ...]] = (
    ("00-qa-control-plane", "control", True, "elmos_autonomous_qa.trusted_services.control_plane_operation_contract"),
    ("01-project-context-ingestion", "context", False, "elmos_autonomous_qa.trusted_services.project_context_operation_contract"),
    ("02-spec-normalization", "context", False, "elmos_autonomous_qa.context_skills.normalize_specification"),
    ("03-requirement-traceability-graph", "planning", False, "elmos_autonomous_qa.context_skills.build_traceability_graph"),
    ("04-risk-coverage-planning", "planning", False, "elmos_autonomous_qa.context_skills.plan_risk_coverage"),
    ("05-test-model-dsl", "generation", False, "elmos_autonomous_qa.context_skills.compile_test_model"),
    ("06-functional-test-generation", "generation", False, "elmos_autonomous_qa.generators.generate_functional_tests"),
    ("07-api-contract-testing", "generation", False, "elmos_autonomous_qa.generators.plan_api_contract_tests"),
    ("08-data-database-testing", "generation", False, "elmos_autonomous_qa.generators.plan_database_tests"),
    ("09-message-workflow-testing", "generation", False, "elmos_autonomous_qa.generators.plan_message_workflow_tests"),
    ("10-ui-e2e-testing", "generation", False, "elmos_autonomous_qa.generators.plan_ui_e2e_tests"),
    ("11-visual-responsive-testing", "generation", False, "elmos_autonomous_qa.generators.plan_visual_responsive_tests"),
    ("12-accessibility-compatibility-testing", "generation", False, "elmos_autonomous_qa.generators.plan_accessibility_compatibility_tests"),
    ("13-performance-baseline-testing", "generation", False, "elmos_autonomous_qa.generators.plan_performance_baseline_tests"),
    ("14-load-stress-spike-soak-testing", "generation", False, "elmos_autonomous_qa.generators.plan_load_stress_spike_soak_tests"),
    ("15-security-abuse-testing", "generation", False, "elmos_autonomous_qa.generators.plan_security_abuse_tests"),
    ("16-resilience-chaos-recovery-testing", "generation", False, "elmos_autonomous_qa.generators.plan_resilience_chaos_recovery_tests"),
    ("17-test-data-management", "execution", False, "elmos_autonomous_qa.context_skills.prepare_test_data"),
    ("18-environment-orchestration", "execution", False, "elmos_autonomous_qa.context_skills.plan_environment_orchestration"),
    ("19-distributed-test-execution", "execution", False, "elmos_autonomous_qa.advanced_skills.plan_shards"),
    ("20-test-oracle-evidence", "evidence", False, "elmos_autonomous_qa.advanced_skills.verify_evidence"),
    ("21-flaky-test-control", "evidence", False, "elmos_autonomous_qa.advanced_skills.classify_flaky"),
    ("22-defect-triage-rca", "repair", False, "elmos_autonomous_qa.advanced_skills.triage_defects"),
    ("23-repair-planning", "repair", False, "elmos_autonomous_qa.advanced_skills.plan_repair"),
    ("24-safe-code-auto-fix", "repair", True, "external-plan:elmos_autonomous_qa.domain.validate_patch"),
    ("25-test-self-healing", "repair", True, "external-plan:elmos_autonomous_qa.domain.validate_test_heal"),
    ("26-impact-analysis-regression", "repair", False, "elmos_autonomous_qa.advanced_skills.analyze_impact"),
    ("27-mutation-property-fuzz-testing", "generation", False, "elmos_autonomous_qa.advanced_skills.plan_advanced_testing"),
    ("28-quality-gate-release-certification", "gate", False, "elmos_autonomous_qa.gates.evaluate_quality_gate_contract"),
    ("29-reporting-observability", "reporting", False, "elmos_autonomous_qa.advanced_skills.build_report"),
    ("30-checkpoint-resume-idempotency", "control", True, "elmos_autonomous_qa.advanced_skills.create_checkpoint"),
    ("31-runtime-cost-eta", "planning", False, "elmos_autonomous_qa.advanced_skills.estimate_eta"),
    ("32-multilanguage-adapter-sdk", "generation", False, "elmos_autonomous_qa.adapters.execute_adapter_contract"),
    ("33-ci-cd-pr-integration", "publishing", True, "external-plan:elmos_autonomous_qa.domain.plan_ci"),
    ("34-continuous-learning-knowledge-base", "lifecycle", True, "elmos_autonomous_qa.advanced_skills.propose_learning"),
    ("35-governance-approval-audit", "control", False, "elmos_autonomous_qa.advanced_skills.authorize_action"),
    ("36-project-output-contract", "delivery-plan", False, "elmos_autonomous_qa.delivery_skills.plan_project_output_contract"),
    ("37-test-source-materialization", "materialization", True, "elmos_autonomous_qa.delivery_skills.emit_test_sources"),
    ("38-project-output-bundle-publishing", "publishing", True, "elmos_autonomous_qa.delivery_service.publishing_operation_contract"),
    ("39-output-versioning-retention", "lifecycle", True, "elmos_autonomous_qa.delivery_service.lifecycle_operation_contract"),
)


def _build_registry() -> dict[str, HandlerBinding]:
    registry: dict[str, HandlerBinding] = {}
    for ordinal, (source_id, phase, mutating, operation) in enumerate(_SPECS):
        alias = "autonomous-qa-" + source_id
        handler = _make_handler(source_id, operation, mutating=mutating)
        registry[alias] = HandlerBinding(
            ordinal=ordinal,
            source_id=source_id,
            skill=alias,
            handler_id=handler.__name__,
            phase=phase,
            mutating=mutating,
            operation_id=_operation_identity(operation),
            handler=handler,
        )
    return registry


SKILL_REGISTRY: Final[Mapping[str, HandlerBinding]] = MappingProxyType(_build_registry())
SOURCE_ID_TO_ALIAS: Final[Mapping[str, str]] = MappingProxyType(
    {binding.source_id: binding.skill for binding in SKILL_REGISTRY.values()}
)


def resolve_skill(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SkillRuntimeError("autonomous QA Skill identity must be a bounded string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise SkillRuntimeError("autonomous QA Skill identity is not valid Unicode") from exc
    if len(encoded) > 128:
        raise SkillRuntimeError("autonomous QA Skill identity must be a bounded string")
    if value in SKILL_REGISTRY:
        return value
    alias = SOURCE_ID_TO_ALIAS.get(value)
    if alias is None:
        raise SkillRuntimeError(f"unknown autonomous QA Skill: {value}")
    return alias


def _request_document(request: RuntimeRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "request_id": request.request_id,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "actor_id": request.actor_id,
        "idempotency_key": request.idempotency_key,
        "trace_id": request.trace_id,
        "inputs": request.inputs,
        "policy": request.policy,
        "capabilities": request.capabilities,
    }


def _fallback_request(
    request: Mapping[str, Any], *, prefix: str
) -> RuntimeRequest:
    try:
        return RuntimeRequest.parse(
            {
                "schema_version": "1.0",
                "request_id": request.get("request_id", f"{prefix}-request"),
                "tenant_id": request.get("tenant_id", f"{prefix}-tenant"),
                "project_id": request.get("project_id", f"{prefix}-project"),
                "inputs": {},
            }
        )
    except Exception:
        return RuntimeRequest.parse(
            {
                "schema_version": "1.0",
                "request_id": f"{prefix}-request",
                "tenant_id": f"{prefix}-tenant",
                "project_id": f"{prefix}-project",
                "inputs": {},
            }
        )


def _raw_request_digest(request: Mapping[str, Any]) -> str | None:
    try:
        return digest_json(strict_json(request, "rejected request"))
    except Exception:
        return None


def dispatch_skill(skill: str, request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate, dispatch, and normalize one exact Skill request."""

    try:
        alias = resolve_skill(skill)
    except SkillRuntimeError:
        raise
    binding = SKILL_REGISTRY[alias]
    normalized: RuntimeRequest | None = None
    try:
        normalized = RuntimeRequest.parse(request)
        operation = binding.handler(normalized)
        return normalize_result(
            skill=alias,
            source_id=binding.source_id,
            handler_id=binding.handler_id,
            operation_id=binding.operation_id,
            phase=binding.phase,
            mutating=binding.mutating,
            request=normalized,
            operation=operation,
        )
    except HandlerOutputError as exc:
        if normalized is None:
            normalized = _fallback_request(request, prefix="failed")
            request_binding = "UNAVAILABLE"
            bound_digest = None
        else:
            request_binding = "EXACT_NORMALIZED"
            bound_digest = digest_json(_request_document(normalized))
        return normalize_result(
            skill=alias,
            source_id=binding.source_id,
            handler_id=binding.handler_id,
            operation_id=binding.operation_id,
            phase=binding.phase,
            mutating=binding.mutating,
            request=normalized,
            operation={
                "state": "FAILED",
                "code": "LOCAL_HANDLER_OUTPUT_INVALID",
                "outputs": {
                    "error_type": type(exc).__name__,
                    "request_binding": request_binding,
                    "failed_request_digest": bound_digest,
                },
                "implementation_state": "LOCAL_VALIDATED",
            },
        )
    except (ContractError, adapters.AdapterContractError) as exc:
        raw_digest = _raw_request_digest(request)
        request_binding = "EXACT_NORMALIZED" if normalized is not None else (
            "RAW_CANONICAL" if raw_digest is not None else "UNAVAILABLE"
        )
        if normalized is None:
            normalized = _fallback_request(request, prefix="rejected")
        bound_digest = (
            digest_json(_request_document(normalized))
            if request_binding == "EXACT_NORMALIZED"
            else raw_digest
        )
        return normalize_result(
            skill=alias,
            source_id=binding.source_id,
            handler_id=binding.handler_id,
            operation_id=binding.operation_id,
            phase=binding.phase,
            mutating=binding.mutating,
            request=normalized,
            operation={
                "state": "BLOCKED",
                "code": "REQUEST_CONTRACT_REJECTED",
                "outputs": {
                    "error_type": type(exc).__name__,
                    "request_binding": request_binding,
                    "rejected_request_digest": bound_digest,
                },
                "implementation_state": "LOCAL_VALIDATED",
            },
        )
    except Exception as exc:  # fail closed without leaking tool/provider details
        raw_digest = _raw_request_digest(request)
        request_binding = "EXACT_NORMALIZED" if normalized is not None else (
            "RAW_CANONICAL" if raw_digest is not None else "UNAVAILABLE"
        )
        if normalized is None:
            normalized = _fallback_request(request, prefix="failed")
        bound_digest = (
            digest_json(_request_document(normalized))
            if request_binding == "EXACT_NORMALIZED"
            else raw_digest
        )
        return normalize_result(
            skill=alias,
            source_id=binding.source_id,
            handler_id=binding.handler_id,
            operation_id=binding.operation_id,
            phase=binding.phase,
            mutating=binding.mutating,
            request=normalized,
            operation={
                "state": "FAILED",
                "code": "LOCAL_HANDLER_FAILED",
                "outputs": {
                    "error_type": type(exc).__name__,
                    "request_binding": request_binding,
                    "failed_request_digest": bound_digest,
                },
                "implementation_state": "LOCAL_VALIDATED",
            },
        )


def validate_skill_registry() -> None:
    bindings = list(SKILL_REGISTRY.values())
    observed_contract = tuple(
        (source_id, phase, mutating, _operation_identity(operation))
        for source_id, phase, mutating, operation in _SPECS
    )
    if observed_contract != CANONICAL_BINDING_CONTRACT:
        raise SkillRuntimeError("runtime binding contract differs from the canonical 40 rows")
    expected_registry = tuple(
        (
            ordinal,
            source_id,
            "autonomous-qa-" + source_id,
            "execute_" + source_id.replace("-", "_"),
            phase,
            mutating,
            operation_id,
        )
        for ordinal, (source_id, phase, mutating, operation_id) in enumerate(
            CANONICAL_BINDING_CONTRACT
        )
    )
    observed_registry = tuple(
        (
            binding.ordinal,
            binding.source_id,
            binding.skill,
            binding.handler_id,
            binding.phase,
            binding.mutating,
            binding.operation_id,
        )
        for binding in bindings
    )
    if observed_registry != expected_registry:
        raise SkillRuntimeError("actual registry differs from the canonical binding contract")
    if tuple(SKILL_REGISTRY) != tuple(row[2] for row in expected_registry):
        raise SkillRuntimeError("registry mapping keys differ from canonical Skill aliases")
    if len(bindings) != 40:
        raise SkillRuntimeError("runtime must bind exactly 40 Skills")
    if sorted(binding.ordinal for binding in bindings) != list(range(40)):
        raise SkillRuntimeError("runtime ordinals must be contiguous")
    if len({binding.source_id for binding in bindings}) != 40:
        raise SkillRuntimeError("source IDs must be unique")
    if len({binding.handler_id for binding in bindings}) != 40:
        raise SkillRuntimeError("handler IDs must be unique")
    if len({id(binding.handler) for binding in bindings}) != 40:
        raise SkillRuntimeError("each Skill must own an exact callable")
    if any(
        not callable(binding.handler)
        or binding.handler.__name__ != binding.handler_id
        or binding.handler.__qualname__ != binding.handler_id
        or binding.handler.__module__ != __name__
        for binding in bindings
    ):
        raise SkillRuntimeError("registry callable metadata differs from its exact binding")
    if any(len(binding.skill) > 64 for binding in bindings):
        raise SkillRuntimeError("installed Skill alias exceeds 64 characters")


def phase_execution_plan() -> tuple[str, ...]:
    indegree = {phase: 0 for phase in PHASE_DAG}
    for targets in PHASE_DAG.values():
        for target in targets:
            indegree[target] += 1
    ready = sorted(phase for phase, degree in indegree.items() if degree == 0)
    plan: list[str] = []
    while ready:
        phase = ready.pop(0)
        plan.append(phase)
        for target in PHASE_DAG[phase]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(plan) != len(PHASE_DAG):
        raise SkillRuntimeError("runtime phase DAG contains a cycle")
    return tuple(plan)


validate_skill_registry()
