"""Immutable model and Skill catalogs owned by this bounded runtime."""

from __future__ import annotations

from dataclasses import dataclass


MODEL_ALIASES: tuple[str, ...] = (
    "gpt-5.6-sol-max",
    "claude-opus-5-max",
    "claude-fable-5",
    "grok-4.6",
    "kimi-k3-max",
    "glm-5.3-max",
    "qwen3.8-max",
    "deepseek-v4-pro-0813",
    "gemini-3.7-flash-high",
    "claude-sonnet-5",
)
MODEL_ALIAS_SET = frozenset(MODEL_ALIASES)


@dataclass(frozen=True, slots=True)
class SkillSpec:
    name: str
    handler: str
    canonical_owner: str
    adapter_requirement: str | None = None
    evidence_boundary: str = (
        "Local deterministic execution is engineering evidence only; "
        "external execution remains NOT_RUN and certification NOT_CERTIFIED."
    )


_SPECS: tuple[SkillSpec, ...] = (
    SkillSpec("elmos-repository-orchestrator", "repository_orchestrator", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-requirement-normalizer", "requirement_normalizer", "canonical.elmos.requirement-baseline"),
    SkillSpec("elmos-repo-intake", "repo_intake", "canonical.elmos.repository-snapshot", "repository"),
    SkillSpec("elmos-architecture-indexer", "architecture_indexer", "canonical.elmos.semantic-index"),
    SkillSpec("elmos-change-impact-analyzer", "change_impact_analyzer", "canonical.elmos.impact-graph"),
    SkillSpec("elmos-task-decomposer", "task_decomposer", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-atomicity-validator", "atomicity_validator", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-task-dag-builder", "task_dag_builder", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-contract-boundary-generator", "contract_boundary_generator", "canonical.elmos.contract-registry"),
    SkillSpec("elmos-complexity-estimator", "complexity_estimator", "canonical.elmos.execution-intelligence"),
    SkillSpec("elmos-risk-classifier", "risk_classifier", "canonical.elmos.identity-policy"),
    SkillSpec("elmos-context-slicer", "context_slicer", "canonical.elmos.context-builder"),
    SkillSpec("elmos-model-registry-guard", "model_registry_guard", "canonical.elmos.model-gateway"),
    SkillSpec("elmos-model-capability-profiler", "model_capability_profiler", "canonical.elmos.model-gateway"),
    SkillSpec("elmos-cost-performance-router", "cost_performance_router", "canonical.elmos.model-gateway"),
    SkillSpec("elmos-budget-planner", "budget_planner", "canonical.elmos.budget-ledger"),
    SkillSpec("elmos-eta-estimator", "eta_estimator", "canonical.elmos.execution-intelligence"),
    SkillSpec("elmos-wave-scheduler", "wave_scheduler", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-worktree-manager", "worktree_manager", "canonical.elmos.workspace-scm", "worktree"),
    SkillSpec("elmos-worker-prompt-builder", "worker_prompt_builder", "canonical.elmos.context-builder"),
    SkillSpec("elmos-worker-executor", "worker_executor", "canonical.elmos.model-gateway", "provider"),
    SkillSpec("elmos-deterministic-validator", "deterministic_validator", "canonical.elmos.runner", "runner"),
    SkillSpec("elmos-failure-classifier", "failure_classifier", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-retry-escalation-controller", "retry_escalation_controller", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-patch-reviewer", "patch_reviewer", "canonical.elmos.verification-fabric", "provider"),
    SkillSpec("elmos-security-auth-gate", "security_auth_gate", "canonical.elmos.verification-fabric", "external"),
    SkillSpec("elmos-data-migration-gate", "data_migration_gate", "canonical.elmos.verification-fabric", "external"),
    SkillSpec("elmos-concurrency-idempotency-gate", "concurrency_idempotency_gate", "canonical.elmos.verification-fabric", "external"),
    SkillSpec("elmos-integration-manager", "integration_manager", "canonical.elmos.workspace-scm", "scm"),
    SkillSpec("elmos-conflict-resolver", "conflict_resolver", "canonical.elmos.workspace-scm", "scm"),
    SkillSpec("elmos-incremental-regression-gate", "incremental_regression_gate", "canonical.elmos.runner", "runner"),
    SkillSpec("elmos-repository-certifier", "repository_certifier", "canonical.elmos.local-verification-gate"),
    SkillSpec("elmos-rollback-recovery", "rollback_recovery", "canonical.elmos.workspace-scm", "scm"),
    SkillSpec("elmos-run-state-journal", "run_state_journal", "canonical.elmos.durable-runtime"),
    SkillSpec("elmos-telemetry-learner", "telemetry_learner", "canonical.elmos.execution-intelligence"),
    SkillSpec("elmos-routing-policy-optimizer", "routing_policy_optimizer", "canonical.elmos.model-gateway"),
    SkillSpec("elmos-model-selection-controller", "model_selection_controller", "canonical.elmos.model-gateway"),
)

SKILL_SPECS = {spec.name: spec for spec in _SPECS}
SKILL_NAMES: tuple[str, ...] = tuple(spec.name for spec in _SPECS)

if len(SKILL_NAMES) != 37 or len(SKILL_SPECS) != 37:
    raise RuntimeError("repository-orchestrator catalog must contain exactly 37 unique Skills")

