"""Exact runtime registry and orchestration boundary for all PDHI v1 Skills.

This registry is repository-owned.  It binds every one of the 260 canonical
capabilities to an explicit typed implementation surface while retaining all
262 source occurrences.  It does not treat the source catalog as executable
authority and it never invents source task IDs or dependency edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from ._catalog import SOURCE_CAPABILITY_CATALOG
from .agent_runtime import K4_OPERATION_BINDINGS
from .assurance import K5_OPERATION_BINDINGS
from .canonical import digest_object
from .control_plane import K9_OPERATION_BINDINGS
from .evolution import K7_CAPABILITY_BINDINGS
from .policy import K6_OPERATION_BINDINGS
from .registry import (
    CAPABILITY_OCCURRENCES,
    CAPABILITY_REGISTRY,
    SKILL_REGISTRY,
    CapabilityResolution,
    resolve_operation,
    resolve_skill,
)
from .routing import K8_CAPABILITY_BINDINGS
from .runtime_proof import K3_OPERATION_SPECS
from .semantic import K1_OPERATION_SPECS
from .transactions import K2_OPERATION_SPECS


class RuntimeStatus(StrEnum):
    LOCAL = "LOCAL"
    PARTIAL = "PARTIAL_EXTERNAL_EFFECT_NOT_RUN"


@dataclass(frozen=True, slots=True)
class RuntimeBinding:
    operation_id: str
    operation: str
    owner: str
    handler: str
    input_contract: str
    output_contract: str
    runtime_status: RuntimeStatus
    external_effect_status: str
    certification_status: str
    source_occurrence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "operation": self.operation,
            "owner": self.owner,
            "handler": self.handler,
            "input_contract": self.input_contract,
            "output_contract": self.output_contract,
            "runtime_status": self.runtime_status.value,
            "external_effect_status": self.external_effect_status,
            "certification_status": self.certification_status,
            "source_occurrence_ids": list(self.source_occurrence_ids),
        }


@dataclass(frozen=True, slots=True)
class SkillRuntimeBinding:
    skill_id: str
    skill_name: str
    source_owner: str
    entrypoint: str
    runtime_status: RuntimeStatus
    external_effect_status: str = "NOT_RUN"
    certification_status: str = "NOT_CERTIFIED"


_KERNEL_SKILL_ENTRYPOINTS: Mapping[str, str] = MappingProxyType(
    {
        "elmos-proof-driven-harness-intelligence": "PdhiOrchestrator",
        "elmos-harness-contracts": "elmos_pdhi.contracts",
        "elmos-repository-semantic-intelligence": "SemanticRuntime",
        "elmos-transactional-semantic-transformation": "TransactionManager",
        "elmos-runtime-equivalence-proof": "RuntimeProofService",
        "elmos-agentic-execution-runtime": "AgentTaskDAG+AgentSupervisor",
        "elmos-independent-assurance": "ReleaseVerdictReviewer",
        "elmos-policy-invariant-engine": "PolicyDecisionPoint+PolicyEnforcementPoint",
        "elmos-certified-skill-evolution": "SkillEvolutionService",
        "elmos-harness-intelligence": "ToolAuthorityRouter+ModelRoleRouter+AppendOnlyContextLedger",
        "elmos-production-control-plane": "ProductionControlPlane",
        "elmos-e0-e5-harness-certification": "CertificationEvaluator",
    }
)


def _status(external: bool) -> tuple[RuntimeStatus, str]:
    return (
        RuntimeStatus.PARTIAL if external else RuntimeStatus.LOCAL,
        "NOT_RUN" if external else "NOT_APPLICABLE_LOCAL_ONLY",
    )


def _binding(
    operation: str,
    *,
    owner: str,
    handler: str,
    input_contract: str,
    output_contract: str,
    external: bool,
) -> RuntimeBinding:
    canonical = CAPABILITY_REGISTRY[operation]
    if canonical.canonical_owner != owner:
        raise RuntimeError(f"runtime owner drift for {operation}: {owner} != {canonical.canonical_owner}")
    runtime_status, external_status = _status(external)
    return RuntimeBinding(
        operation_id=canonical.operation_id,
        operation=operation,
        owner=owner,
        handler=handler,
        input_contract=input_contract,
        output_contract=output_contract,
        runtime_status=runtime_status,
        external_effect_status=external_status,
        certification_status="NOT_CERTIFIED",
        source_occurrence_ids=canonical.occurrence_ids,
    )


def _build_runtime_bindings() -> Mapping[str, RuntimeBinding]:
    result: dict[str, RuntimeBinding] = {}
    for name, k1_spec in K1_OPERATION_SPECS.items():
        result[name] = _binding(
            name,
            owner="K1",
            handler=f"SemanticRuntime.{k1_spec.method}",
            input_contract="typed K1 arguments",
            output_contract=k1_spec.output_contract,
            external=k1_spec.external_adapter,
        )
    for name, k2_spec in K2_OPERATION_SPECS.items():
        result[name] = _binding(
            name,
            owner="K2",
            handler=f"TransactionManager.{k2_spec.method}",
            input_contract="typed K2 arguments",
            output_contract=k2_spec.output_contract,
            external=k2_spec.external_adapter,
        )
    for name, k3_spec in K3_OPERATION_SPECS.items():
        result[name] = _binding(
            name,
            owner="K3",
            handler=f"RuntimeProofService.{k3_spec.method}",
            input_contract="typed K3 arguments",
            output_contract=k3_spec.output_contract,
            external=k3_spec.external_adapter,
        )
    for name, k4_binding in K4_OPERATION_BINDINGS.items():
        if k4_binding.canonical_owner != "K4":
            continue
        result[name] = _binding(
            name,
            owner="K4",
            handler=k4_binding.handler,
            input_contract=k4_binding.input_contract,
            output_contract=k4_binding.output_contract,
            external=k4_binding.external_effect,
        )
    for owner, source in (("K5", K5_OPERATION_BINDINGS), ("K6", K6_OPERATION_BINDINGS)):
        for name, assurance_binding in source.items():
            result[name] = _binding(
                name,
                owner=owner,
                handler=assurance_binding.handler,
                input_contract=assurance_binding.input_contract,
                output_contract=assurance_binding.output_contract,
                external=assurance_binding.external_effect,
            )
    k7_external = {"skill-certifier", "skill-promoter", "skill-canary", "skill-rollback"}
    for name, handler in K7_CAPABILITY_BINDINGS.items():
        result[name] = _binding(
            name,
            owner="K7",
            handler=handler,
            input_contract="typed K7 domain arguments",
            output_contract="typed K7 domain result",
            external=name in k7_external,
        )
    k8_external = {
        "tool-capability-negotiator",
        "provider-failure-fallback",
        "credential-pool-affinity",
        "provider-stream-reset",
        "foreign-session-import",
    }
    for name, handler in K8_CAPABILITY_BINDINGS.items():
        result[name] = _binding(
            name,
            owner="K8",
            handler=handler,
            input_contract="typed K8 policy/context arguments",
            output_contract="typed K8 route/context decision",
            external=name in k8_external,
        )
    for name, k9_binding in K9_OPERATION_BINDINGS.items():
        result[name] = _binding(
            name,
            owner="K9",
            handler=k9_binding.handler,
            input_contract="Invocation",
            output_contract="ControlPlaneOutcome",
            external=k9_binding.external_effect,
        )
    return MappingProxyType(result)


RUNTIME_BINDINGS = _build_runtime_bindings()
SKILL_RUNTIME_BINDINGS: Mapping[str, SkillRuntimeBinding] = MappingProxyType(
    {
        name: SkillRuntimeBinding(
            skill_id=skill.skill_id,
            skill_name=name,
            source_owner=skill.source_owner,
            entrypoint=_KERNEL_SKILL_ENTRYPOINTS[name],
            runtime_status=(
                RuntimeStatus.PARTIAL
                if skill.source_owner in {"ORCHESTRATOR", "K3", "K4", "K5", "K7", "K8", "K9", "K10"}
                else RuntimeStatus.LOCAL
            ),
        )
        for name, skill in SKILL_REGISTRY.items()
    }
)


DERIVED_RUNTIME_DEPENDENCIES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "K0": (),
        "K1": ("K0",),
        "K2": ("K0", "K1"),
        "K3": ("K0", "K1", "K2"),
        "K4": ("K0", "K1", "K2", "K3"),
        "K5": ("K0", "K1", "K3", "K4"),
        "K6": ("K0", "K1", "K4", "K5"),
        "K7": ("K0", "K1", "K3", "K5", "K6"),
        "K8": ("K0", "K1", "K4", "K6"),
        "K9": ("K0", "K4", "K5", "K6", "K8"),
        "K10": ("K0", "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9"),
    }
)


class RuntimeRegistry:
    """Resolve exact capability and Skill implementations without fallback."""

    def resolve_operation(self, operation: str, *, source_owner: str | None = None) -> RuntimeBinding:
        resolution: CapabilityResolution = resolve_operation(operation, owner=source_owner)
        binding = RUNTIME_BINDINGS.get(resolution.operation.name)
        if binding is None:
            raise RuntimeError(f"allowlisted operation is not runtime bound: {operation}")
        return binding

    def resolve_skill(self, skill: str) -> SkillRuntimeBinding:
        resolved = resolve_skill(skill)
        return SKILL_RUNTIME_BINDINGS[resolved.name]

    def manifest(self) -> Mapping[str, Any]:
        local = sum(item.runtime_status is RuntimeStatus.LOCAL for item in RUNTIME_BINDINGS.values())
        partial = len(RUNTIME_BINDINGS) - local
        body = {
            "schema_version": "1.0.0",
            "namespace": "elmos.pdhi.v1",
            "source_skill_count": len(SKILL_REGISTRY),
            "canonical_operation_count": len(RUNTIME_BINDINGS),
            "source_occurrence_count": len(CAPABILITY_OCCURRENCES),
            "source_task_id_count": 0,
            "source_dependency_edge_count": 0,
            "derived_runtime_dependency_kind": "REPOSITORY_DERIVED_NOT_SOURCE_DECLARED",
            "derived_runtime_dependencies": dict(DERIVED_RUNTIME_DEPENDENCIES),
            "runtime_counts": {"LOCAL": local, "PARTIAL": partial, "PLAN": 0},
            "skills": {
                name: {
                    "skill_id": item.skill_id,
                    "entrypoint": item.entrypoint,
                    "runtime_status": item.runtime_status.value,
                    "external_evidence_status": item.external_effect_status,
                    "certification_status": item.certification_status,
                }
                for name, item in SKILL_RUNTIME_BINDINGS.items()
            },
            "operations": [binding.to_dict() for binding in RUNTIME_BINDINGS.values()],
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        return MappingProxyType(
            {**body, "manifest_digest": digest_object(body, domain="pdhi-runtime-manifest")}
        )


if len(RUNTIME_BINDINGS) != 260 or set(RUNTIME_BINDINGS) != set(CAPABILITY_REGISTRY):
    raise RuntimeError(
        f"PDHI runtime must bind exactly 260 canonical capabilities; got {len(RUNTIME_BINDINGS)}"
    )
if len(SKILL_RUNTIME_BINDINGS) != 12 or set(SKILL_RUNTIME_BINDINGS) != set(SKILL_REGISTRY):
    raise RuntimeError("PDHI runtime must bind all 12 source Skills exactly")
for owner, names in SOURCE_CAPABILITY_CATALOG.items():
    for name in names:
        if name not in RUNTIME_BINDINGS:
            raise RuntimeError(f"source occurrence lacks a canonical runtime binding: {owner}:{name}")


__all__ = [
    "DERIVED_RUNTIME_DEPENDENCIES",
    "RUNTIME_BINDINGS",
    "RuntimeBinding",
    "RuntimeRegistry",
    "RuntimeStatus",
    "SKILL_RUNTIME_BINDINGS",
    "SkillRuntimeBinding",
]
