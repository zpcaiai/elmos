"""Exact registry for the FDE autonomous-delivery capability package.

The source ZIP is a specification, not runtime authority.  This module is the
repository-owned allowlist that binds each of the 45 atomic identities to one
distinct Python callable.  Dependency order is copied from the pinned 5.2.0
catalog and is validated at import time so a drifted or cyclic registry cannot
silently activate.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final


PACKAGE_NAME: Final = "elmos-fde-autonomous-delivery-repository-refactoring-skills"
PACKAGE_VERSION: Final = "5.2.0"
ARCHIVE_SHA256: Final = "4dbd6f20b0d27dbacf12ed432f0486f9e59151c2b138c6e7d8a9f60f395b1428"
ALIAS_PREFIX: Final = "elmos-fde-"


class EffectClass(StrEnum):
    """Maximum effect a local handler may prepare, never self-authorize."""

    READ_ONLY = "READ_ONLY"
    PREPARE_WORKSPACE_MUTATION = "PREPARE_WORKSPACE_MUTATION"
    PREPARE_EXTERNAL_EFFECT = "PREPARE_EXTERNAL_EFFECT"


@dataclass(frozen=True, slots=True)
class SkillBinding:
    source_id: str
    alias: str
    pack: str
    module: str
    handler: str
    dependencies: tuple[str, ...]
    effect_class: EffectClass
    required_adapters: tuple[str, ...]
    implementation_state: str = "LOCAL_CONTROL_PLANE"
    external_evidence: str = "NOT_RUN"
    independent_evidence: str = "NOT_RUN"
    certification: str = "NOT_CERTIFIED"


PACK_BY_SKILL: Final = MappingProxyType(
    {
        **{name: "01-fde-engagement" for name in (
            "stakeholder-workflow-discovery", "business-baseline-roi",
            "pilot-scope-sow-acceptance", "status-risk-decision-communications",
            "procurement-security-questionnaire", "adoption-change-management",
        )},
        **{name: "02-repository-intake-runtime" for name in (
            "repository-custody-and-revisionset", "asset-inventory-and-classification",
            "reproducible-build-environment",
            "external-dependency-stub-and-service-virtualization",
            "support-profile-and-unknown-register",
            "runtime-observation-and-traffic-capture",
        )},
        **{name: "03-semantic-intelligence" for name in (
            "polyglot-semantic-system-graph", "business-capability-code-mapping",
            "data-event-permission-lineage", "git-history-ownership-change-coupling",
            "static-dynamic-evidence-fusion",
        )},
        **{name: "04-unified-assessment" for name in (
            "issue-ontology-and-finding-normalization",
            "architecture-maintainability-audit",
            "correctness-concurrency-consistency-audit",
            "security-privacy-supply-chain-audit", "data-database-migration-audit",
            "performance-reliability-observability-audit",
            "test-ci-cd-developer-experience-audit", "ux-accessibility-i18n-audit",
            "ai-agent-system-audit", "cost-finops-sustainability-audit",
        )},
        **{name: "05-planning-transformation" for name in (
            "root-cause-risk-prioritization", "business-invariant-recovery",
            "target-architecture-alternatives-and-adr", "transformation-dag-estimation",
            "changeset-commit-and-provenance-governance",
            "proof-guided-atomic-refactor-execution",
            "modernization-strangler-and-rearchitecture",
            "cross-language-framework-transformation",
            "database-schema-routine-data-transformation",
        )},
        **{name: "06-verification-release-operations" for name in (
            "characterization-differential-mutation-verification",
            "formal-assurance-routing", "e0-e3-readiness-and-evidence-bundle",
            "shadow-dual-run-canary-rollback-preparation",
            "incident-triage-remediation-and-postmortem",
            "final-handoff-training-support", "reusable-recipe-skill-learning",
            "portfolio-multi-repository-governance", "product-feedback-roadmap-loop",
        )},
    }
)


DEPENDENCIES: Final = MappingProxyType(
    {
        "stakeholder-workflow-discovery": (),
        "business-baseline-roi": ("stakeholder-workflow-discovery",),
        "pilot-scope-sow-acceptance": ("stakeholder-workflow-discovery", "business-baseline-roi"),
        "status-risk-decision-communications": ("pilot-scope-sow-acceptance",),
        "procurement-security-questionnaire": ("status-risk-decision-communications",),
        "adoption-change-management": ("pilot-scope-sow-acceptance",),
        "repository-custody-and-revisionset": (),
        "asset-inventory-and-classification": ("repository-custody-and-revisionset",),
        "reproducible-build-environment": ("asset-inventory-and-classification",),
        "external-dependency-stub-and-service-virtualization": ("reproducible-build-environment",),
        "support-profile-and-unknown-register": ("asset-inventory-and-classification",),
        "runtime-observation-and-traffic-capture": ("reproducible-build-environment",),
        "polyglot-semantic-system-graph": ("reproducible-build-environment", "support-profile-and-unknown-register"),
        "business-capability-code-mapping": ("stakeholder-workflow-discovery", "polyglot-semantic-system-graph"),
        "data-event-permission-lineage": ("polyglot-semantic-system-graph",),
        "git-history-ownership-change-coupling": ("repository-custody-and-revisionset", "asset-inventory-and-classification"),
        "static-dynamic-evidence-fusion": ("polyglot-semantic-system-graph", "runtime-observation-and-traffic-capture", "git-history-ownership-change-coupling"),
        "issue-ontology-and-finding-normalization": ("static-dynamic-evidence-fusion", "support-profile-and-unknown-register"),
        "architecture-maintainability-audit": ("issue-ontology-and-finding-normalization", "business-capability-code-mapping", "git-history-ownership-change-coupling"),
        "correctness-concurrency-consistency-audit": ("issue-ontology-and-finding-normalization", "data-event-permission-lineage"),
        "security-privacy-supply-chain-audit": ("issue-ontology-and-finding-normalization", "data-event-permission-lineage", "reproducible-build-environment"),
        "data-database-migration-audit": ("issue-ontology-and-finding-normalization", "data-event-permission-lineage"),
        "performance-reliability-observability-audit": ("issue-ontology-and-finding-normalization", "runtime-observation-and-traffic-capture"),
        "test-ci-cd-developer-experience-audit": ("issue-ontology-and-finding-normalization", "reproducible-build-environment", "business-capability-code-mapping"),
        "ux-accessibility-i18n-audit": ("issue-ontology-and-finding-normalization", "business-capability-code-mapping"),
        "ai-agent-system-audit": ("issue-ontology-and-finding-normalization", "data-event-permission-lineage", "test-ci-cd-developer-experience-audit"),
        "cost-finops-sustainability-audit": ("status-risk-decision-communications", "performance-reliability-observability-audit"),
        "root-cause-risk-prioritization": ("architecture-maintainability-audit", "correctness-concurrency-consistency-audit", "security-privacy-supply-chain-audit", "data-database-migration-audit", "performance-reliability-observability-audit"),
        "business-invariant-recovery": ("business-capability-code-mapping", "root-cause-risk-prioritization"),
        "target-architecture-alternatives-and-adr": ("root-cause-risk-prioritization", "business-invariant-recovery"),
        "transformation-dag-estimation": ("target-architecture-alternatives-and-adr",),
        "changeset-commit-and-provenance-governance": ("transformation-dag-estimation",),
        "proof-guided-atomic-refactor-execution": ("changeset-commit-and-provenance-governance",),
        "modernization-strangler-and-rearchitecture": ("proof-guided-atomic-refactor-execution", "target-architecture-alternatives-and-adr"),
        "cross-language-framework-transformation": ("proof-guided-atomic-refactor-execution", "business-invariant-recovery"),
        "database-schema-routine-data-transformation": ("proof-guided-atomic-refactor-execution", "data-database-migration-audit", "business-invariant-recovery"),
        "characterization-differential-mutation-verification": ("proof-guided-atomic-refactor-execution", "business-invariant-recovery"),
        "formal-assurance-routing": ("business-invariant-recovery", "correctness-concurrency-consistency-audit"),
        "e0-e3-readiness-and-evidence-bundle": ("characterization-differential-mutation-verification", "security-privacy-supply-chain-audit", "performance-reliability-observability-audit", "test-ci-cd-developer-experience-audit"),
        "shadow-dual-run-canary-rollback-preparation": ("e0-e3-readiness-and-evidence-bundle", "changeset-commit-and-provenance-governance"),
        "incident-triage-remediation-and-postmortem": ("runtime-observation-and-traffic-capture", "shadow-dual-run-canary-rollback-preparation"),
        "final-handoff-training-support": ("adoption-change-management", "e0-e3-readiness-and-evidence-bundle"),
        "reusable-recipe-skill-learning": ("incident-triage-remediation-and-postmortem", "e0-e3-readiness-and-evidence-bundle"),
        "portfolio-multi-repository-governance": ("reusable-recipe-skill-learning", "support-profile-and-unknown-register"),
        "product-feedback-roadmap-loop": ("status-risk-decision-communications", "adoption-change-management", "reusable-recipe-skill-learning"),
    }
)


_MODULE_BY_PACK: Final = {
    "01-fde-engagement": "elmos_fde_delivery.handlers.engagement",
    "02-repository-intake-runtime": "elmos_fde_delivery.handlers.intake",
    "03-semantic-intelligence": "elmos_fde_delivery.handlers.semantic",
    "04-unified-assessment": "elmos_fde_delivery.handlers.assessment",
    "05-planning-transformation": "elmos_fde_delivery.handlers.transformation",
    "06-verification-release-operations": "elmos_fde_delivery.handlers.operations",
}

_WORKSPACE_PREPARE: Final = frozenset(
    {
        "changeset-commit-and-provenance-governance",
        "proof-guided-atomic-refactor-execution",
        "modernization-strangler-and-rearchitecture",
        "cross-language-framework-transformation",
        "database-schema-routine-data-transformation",
    }
)
_EXTERNAL_PREPARE: Final = frozenset(
    {
        "repository-custody-and-revisionset",
        "reproducible-build-environment",
        "external-dependency-stub-and-service-virtualization",
        "runtime-observation-and-traffic-capture",
        "procurement-security-questionnaire",
        "status-risk-decision-communications",
        "shadow-dual-run-canary-rollback-preparation",
        "incident-triage-remediation-and-postmortem",
        "final-handoff-training-support",
        "product-feedback-roadmap-loop",
    }
)
_ADAPTERS: Final = MappingProxyType(
    {
        "repository-custody-and-revisionset": ("git-provider-adapter", "artifact-storage-adapter"),
        "reproducible-build-environment": ("sandbox-executor-adapter", "compiler-lsp-adapter", "test-runner-adapter"),
        "external-dependency-stub-and-service-virtualization": ("service-virtualization-adapter",),
        "runtime-observation-and-traffic-capture": ("observability-adapter",),
        "procurement-security-questionnaire": ("documentation-adapter",),
        "status-risk-decision-communications": ("communication-adapter",),
        "proof-guided-atomic-refactor-execution": ("compiler-lsp-adapter", "sandbox-executor-adapter", "test-runner-adapter"),
        "cross-language-framework-transformation": ("compiler-lsp-adapter", "sandbox-executor-adapter", "test-runner-adapter"),
        "database-schema-routine-data-transformation": ("database-adapter", "sandbox-executor-adapter", "test-runner-adapter"),
        "shadow-dual-run-canary-rollback-preparation": ("workflow-engine-adapter", "cloud-kubernetes-adapter", "observability-adapter"),
        "incident-triage-remediation-and-postmortem": ("observability-adapter", "communication-adapter"),
        "final-handoff-training-support": ("documentation-adapter", "communication-adapter"),
        "product-feedback-roadmap-loop": ("crm-commercial-adapter", "issue-tracker-adapter"),
    }
)


def _effect_class(skill_id: str) -> EffectClass:
    if skill_id in _WORKSPACE_PREPARE:
        return EffectClass.PREPARE_WORKSPACE_MUTATION
    if skill_id in _EXTERNAL_PREPARE:
        return EffectClass.PREPARE_EXTERNAL_EFFECT
    return EffectClass.READ_ONLY


SKILL_BINDINGS: Final = MappingProxyType(
    {
        skill_id: SkillBinding(
            source_id=skill_id,
            alias=ALIAS_PREFIX + skill_id,
            pack=PACK_BY_SKILL[skill_id],
            module=_MODULE_BY_PACK[PACK_BY_SKILL[skill_id]],
            handler="execute_" + skill_id.replace("-", "_"),
            dependencies=DEPENDENCIES[skill_id],
            effect_class=_effect_class(skill_id),
            required_adapters=_ADAPTERS.get(skill_id, ()),
        )
        for skill_id in DEPENDENCIES
    }
)

WORKFLOW_SKILLS: Final = (
    "elmos-fde-audit-existing-repository",
    "elmos-fde-build-fde-workflow",
    "elmos-fde-build-repository-intelligence",
    "elmos-fde-create-adapter",
    "elmos-fde-execute-refactor",
    "elmos-fde-implement-component-skill",
    "elmos-fde-implement-vertical-slice",
    "elmos-fde-package-navigator",
    "elmos-fde-plan-implementation-wave",
    "elmos-fde-retrospective-and-learn",
    "elmos-fde-run-package-evals",
    "elmos-fde-verify-change",
)


def topological_order() -> tuple[str, ...]:
    """Return the exact deterministic DAG order or fail on registry drift."""

    if set(PACK_BY_SKILL) != set(DEPENDENCIES) or len(DEPENDENCIES) != 45:
        raise RuntimeError("FDE registry cardinality or pack coverage drifted")
    incoming = {name: set(dependencies) for name, dependencies in DEPENDENCIES.items()}
    for name, dependencies in incoming.items():
        missing = dependencies.difference(incoming)
        if missing or name in dependencies:
            raise RuntimeError(f"FDE dependency graph is invalid for {name}: {sorted(missing)}")
    ready = sorted(name for name, dependencies in incoming.items() if not dependencies)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for name in sorted(incoming):
            if current in incoming[name]:
                incoming[name].remove(current)
                if not incoming[name] and name not in ordered and name not in ready:
                    ready.append(name)
        ready.sort()
    if len(ordered) != len(incoming):
        raise RuntimeError("FDE dependency graph contains a cycle")
    return tuple(ordered)


TOPOLOGICAL_ORDER: Final = topological_order()


def describe_registry() -> dict[str, object]:
    return {
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "archive_sha256": "sha256:" + ARCHIVE_SHA256,
        "atomic_skill_count": len(SKILL_BINDINGS),
        "workflow_skill_count": len(WORKFLOW_SKILLS),
        "skills": [
            {
                "source_id": binding.source_id,
                "alias": binding.alias,
                "pack": binding.pack,
                "handler": f"{binding.module}:{binding.handler}",
                "dependencies": list(binding.dependencies),
                "effect_class": binding.effect_class.value,
                "required_adapters": list(binding.required_adapters),
                "implementation_state": binding.implementation_state,
                "external_evidence": binding.external_evidence,
                "independent_evidence": binding.independent_evidence,
                "certification": binding.certification,
            }
            for binding in SKILL_BINDINGS.values()
        ],
        "workflow_skills": list(WORKFLOW_SKILLS),
    }

