---
name: "elmos-budget-planner"
description: "Allocate run budget across implementation, retries, integration and final certification before execution begins."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/15-budget-planner/SKILL.md"
  source_sha256: "sha256:26e4dc6ef488fc2694859b829a2a4e99c992f57947c72d1f4142bbdf388cee94"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "budget_planner"
  canonical_owner: "canonical.elmos.budget-ledger"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/15-budget-planner/SKILL.md` (`sha256:26e4dc6ef488fc2694859b829a2a4e99c992f57947c72d1f4142bbdf388cee94`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Budget Planner

Allocate run budget across implementation, retries, integration and final certification before execution begins.

## Trigger conditions
- DAG + routing priors ready

## Inputs
- `DAG`
- `pricing/credits`
- `budget policy`

## Outputs
- `run budget plan`
- `per-wave budget`
- `reserve`

## Procedure
1. Estimate base cost per task.
2. Reserve escalation and final-certification budget.
3. Compute soft/hard stop thresholds.
4. Prioritize critical-path tasks when constrained.

## Guardrails
- Do not consume certification reserve for noncritical optional work without explicit policy.

## Acceptance criteria
- plan fits hard cap or run reports infeasible

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
