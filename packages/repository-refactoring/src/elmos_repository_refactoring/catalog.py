"""The exact, closed catalog of repository-refactoring Skills.

The dispatcher refuses to run anything that is not listed here, and refuses to
start at all if a declared Skill has no handler.  Coverage is therefore a
structural property of the package rather than something a test has to chase.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import AdapterLevel, ContractError, RiskClass


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """Static declaration of one Skill's identity, risk and dependencies."""

    name: str
    handler: str
    risk_class: RiskClass
    canonical_owner: str
    depends_on: tuple[str, ...]
    mutating: bool
    minimum_adapter_level: AdapterLevel
    outputs: tuple[str, ...]

    @property
    def read_only(self) -> bool:
        return not self.mutating


_SPECS: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="repository-refactor-orchestrator",
        handler="repository_refactor_orchestrator",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.durable-runtime",
        depends_on=(),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("run_state", "plan_digest", "checkpoint", "schedule"),
    ),
    SkillSpec(
        name="repository-discovery",
        handler="repository_discovery",
        risk_class=RiskClass.R0,
        canonical_owner="canonical.elmos.repository-snapshot",
        depends_on=(),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("repository_inventory", "language_inventory", "sensitive_area_map", "discovery_evidence"),
    ),
    SkillSpec(
        name="build-graph-and-environment",
        handler="build_graph_and_environment",
        risk_class=RiskClass.R2,
        canonical_owner="canonical.elmos.build-graph",
        depends_on=("repository-discovery",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L1,
        outputs=("build_graph", "toolchain_lock", "baseline_report", "sandbox_image_spec"),
    ),
    SkillSpec(
        name="semantic-index",
        handler="semantic_index",
        risk_class=RiskClass.R0,
        canonical_owner="canonical.elmos.semantic-index",
        depends_on=("repository-discovery", "build-graph-and-environment"),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L1,
        outputs=("semantic_index_snapshot", "coverage_metrics", "unknown_region_report"),
    ),
    SkillSpec(
        name="refactor-intent-compiler",
        handler="refactor_intent_compiler",
        risk_class=RiskClass.R0,
        canonical_owner="canonical.elmos.intent-baseline",
        depends_on=("semantic-index",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("compiled_intent", "acceptance_predicates", "assumption_register", "scope_policy"),
    ),
    SkillSpec(
        name="change-impact-analysis",
        handler="change_impact_analysis",
        risk_class=RiskClass.R0,
        canonical_owner="canonical.elmos.impact-graph",
        depends_on=("semantic-index", "refactor-intent-compiler"),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("impact_report", "change_closure", "test_selection_plan", "wave_plan", "risk_assessment"),
    ),
    SkillSpec(
        name="recipe-synthesis",
        handler="recipe_synthesis",
        risk_class=RiskClass.R2,
        canonical_owner="canonical.elmos.recipe-registry",
        depends_on=("refactor-intent-compiler", "change-impact-analysis"),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("recipe_set", "recipe_lock", "dry_run_patch", "recipe_test_report"),
    ),
    SkillSpec(
        name="deterministic-transform-executor",
        handler="deterministic_transform_executor",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.transform-runtime",
        depends_on=("recipe-synthesis",),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("patch_set", "changed_symbol_set", "source_map", "transform_evidence"),
    ),
    SkillSpec(
        name="cross-language-contract-refactor",
        handler="cross_language_contract_refactor",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.contract-registry",
        depends_on=("change-impact-analysis", "deterministic-transform-executor", "api-compatibility"),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L3,
        outputs=("contract_migration_plan", "compatibility_adapters", "consumer_matrix", "contract_diff"),
    ),
    SkillSpec(
        name="data-schema-refactor",
        handler="data_schema_refactor",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.data-migration",
        depends_on=("change-impact-analysis", "human-approval-gate", "rollback-and-recovery"),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L3,
        outputs=(
            "schema_migration_plan",
            "migration_files",
            "backfill_workflow",
            "data_validation_report",
            "rollback_plan",
        ),
    ),
    SkillSpec(
        name="distributed-system-refactor",
        handler="distributed_system_refactor",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.service-topology",
        depends_on=("cross-language-contract-refactor", "data-schema-refactor", "performance-preservation"),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L3,
        outputs=("service_boundary_plan", "event_migration_plan", "resilience_tests", "operational_runbook"),
    ),
    SkillSpec(
        name="test-and-verification",
        handler="test_and_verification",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.verification",
        depends_on=("deterministic-transform-executor",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("validation_report", "gate_decisions", "sarif", "test_artifacts", "regression_diff"),
    ),
    SkillSpec(
        name="bounded-auto-repair",
        handler="bounded_auto_repair",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.transform-runtime",
        depends_on=("test-and-verification",),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("repair_attempt_records", "updated_patch_set", "unresolved_failure_report"),
    ),
    SkillSpec(
        name="canary-rollout",
        handler="canary_rollout",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.release-control",
        depends_on=("test-and-verification", "human-approval-gate"),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L3,
        outputs=("changesets", "rollout_plan", "canary_report", "release_evidence"),
    ),
    SkillSpec(
        name="rollback-and-recovery",
        handler="rollback_and_recovery",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.durable-runtime",
        depends_on=("repository-refactor-orchestrator",),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L1,
        outputs=("rollback_execution", "recovered_checkpoint", "incident_report"),
    ),
    SkillSpec(
        name="evidence-and-audit",
        handler="evidence_and_audit",
        risk_class=RiskClass.R0,
        canonical_owner="canonical.elmos.evidence-store",
        depends_on=(),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("evidence_bundle", "signed_manifest", "audit_timeline", "billing_breakdown"),
    ),
    SkillSpec(
        name="recipe-learning-registry",
        handler="recipe_learning_registry",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.recipe-registry",
        depends_on=("evidence-and-audit",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("versioned_recipe", "evaluation_report", "registry_metadata", "revocation_list"),
    ),
    SkillSpec(
        name="human-approval-gate",
        handler="human_approval_gate",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.identity-policy",
        depends_on=(),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L0,
        outputs=("approval_decision", "conditions", "audit_record"),
    ),
    SkillSpec(
        name="performance-preservation",
        handler="performance_preservation",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.verification",
        depends_on=("build-graph-and-environment", "test-and-verification"),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("performance_diff", "profile_diff", "guardrail_decision", "optimization_evidence"),
    ),
    SkillSpec(
        name="security-preservation",
        handler="security_preservation",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.security-control",
        depends_on=("test-and-verification",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("security_diff", "sarif", "sbom_delta", "threat_model_delta"),
    ),
    SkillSpec(
        name="api-compatibility",
        handler="api_compatibility",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.contract-registry",
        depends_on=("semantic-index",),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("api_diff", "compatibility_decision", "adapter_patch", "deprecation_plan"),
    ),
    SkillSpec(
        name="multi-repository-refactor-program",
        handler="multi_repository_refactor_program",
        risk_class=RiskClass.R4,
        canonical_owner="canonical.elmos.durable-runtime",
        depends_on=(
            "repository-refactor-orchestrator",
            "cross-language-contract-refactor",
            "canary-rollout",
        ),
        mutating=False,
        minimum_adapter_level=AdapterLevel.L3,
        outputs=("program_plan", "repository_runs", "wave_dashboard", "adoption_report"),
    ),
    SkillSpec(
        name="ui-and-client-refactor",
        handler="ui_and_client_refactor",
        risk_class=RiskClass.R3,
        canonical_owner="canonical.elmos.client-platform",
        depends_on=("semantic-index", "api-compatibility", "test-and-verification"),
        mutating=True,
        minimum_adapter_level=AdapterLevel.L2,
        outputs=("client_patch_set", "visual_diff", "accessibility_report", "platform_compatibility_matrix"),
    ),
)


SKILL_SPECS: Mapping[str, SkillSpec] = MappingProxyType({spec.name: spec for spec in _SPECS})
SKILL_NAMES: tuple[str, ...] = tuple(spec.name for spec in _SPECS)

#: ``elmos-`` prefixed aliases keep the catalog compatible with the
#: repository-wide Skill naming convention without duplicating identities.
SKILL_ALIASES: Mapping[str, str] = MappingProxyType(
    {f"elmos-{name}": name for name in SKILL_NAMES}
    | {"elmos-repository-refactoring": "repository-refactor-orchestrator"}
)

PACKAGE_NAME = "elmos-repository-refactoring"
PACKAGE_VERSION = "1.0.0"


def resolve_skill_name(name: str) -> str:
    """Map an alias to its canonical Skill name, failing closed on unknowns."""

    if name in SKILL_SPECS:
        return name
    resolved = SKILL_ALIASES.get(name)
    if resolved is None:
        raise ContractError(
            "unknown_skill",
            f"unknown skill '{name}'; the catalog is closed",
            {"known": list(SKILL_NAMES)},
        )
    return resolved


def spec_for(name: str) -> SkillSpec:
    return SKILL_SPECS[resolve_skill_name(name)]


def topological_order() -> tuple[str, ...]:
    """Catalog dependency order; raises if the declared graph has a cycle."""

    pending = {spec.name: set(spec.depends_on) for spec in _SPECS}
    ordered: list[str] = []
    while pending:
        ready = sorted(name for name, deps in pending.items() if not deps - set(ordered))
        if not ready:
            raise ContractError("catalog_cycle", "skill catalog dependency graph contains a cycle")
        for name in ready:
            ordered.append(name)
            del pending[name]
    return tuple(ordered)


def _validate_catalog() -> None:
    seen: set[str] = set()
    for spec in _SPECS:
        if spec.name in seen:
            raise ContractError("duplicate_skill", f"duplicate skill name {spec.name}")
        seen.add(spec.name)
        for dependency in spec.depends_on:
            if dependency not in {item.name for item in _SPECS}:
                raise ContractError(
                    "unknown_dependency",
                    f"skill {spec.name} depends on unknown skill {dependency}",
                )
    topological_order()


_validate_catalog()


__all__ = [
    "PACKAGE_NAME",
    "PACKAGE_VERSION",
    "SKILL_ALIASES",
    "SKILL_NAMES",
    "SKILL_SPECS",
    "SkillSpec",
    "resolve_skill_name",
    "spec_for",
    "topological_order",
]
