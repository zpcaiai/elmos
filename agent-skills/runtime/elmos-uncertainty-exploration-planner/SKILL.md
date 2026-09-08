---
name: "elmos-uncertainty-exploration-planner"
description: "Create bounded read-only or disposable probe tasks to resolve uncertain repository behavior before costly implementation."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/45-uncertainty-exploration-planner/SKILL.md"
  source_sha256: "sha256:cea9716b94ff4a11bb1d6d001d7fc570e050d2e1df0e8ff68abd2f6749686737"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "uncertainty_exploration_planner"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/45-uncertainty-exploration-planner/SKILL.md` (`sha256:cea9716b94ff4a11bb1d6d001d7fc570e050d2e1df0e8ff68abd2f6749686737`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Uncertainty & Exploration Planner

Use cheap probes to reduce uncertainty before committing to a plan.

## Inputs
- ambiguity ledger
- impact confidence
- unknown graph edges
- high-risk plan nodes

## Outputs
- `exploration tasks`
- `expected information gain`
- `replan triggers`

## Procedure
1. Identify uncertainties that materially change architecture, scope, risk or model routing.
2. Prefer read-only inspection, targeted test runs, executable probes, trace capture and minimal throwaway patches.
3. Estimate information gain versus exploration cost.
4. Run the smallest probe that can discriminate between competing plan hypotheses.
5. Write findings into the graph and trigger local replan.

## Guardrails
- Exploration tasks may not silently become production implementation.
- Bound exploration spend by policy.

## Acceptance criteria
- each probe has a decision it is intended to resolve
- findings update downstream planning state

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
