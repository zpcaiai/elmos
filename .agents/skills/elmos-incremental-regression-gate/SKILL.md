---
name: "elmos-incremental-regression-gate"
description: "Run impact-based regression after each wave so defects are caught before the final expensive full-suite gate."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/30-incremental-regression-gate/SKILL.md"
  source_sha256: "sha256:33d977773bc2e57dcd5a523aa3436f5f8297b257768d8a2b3991fc2602d6d8b6"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "incremental_regression_gate"
  canonical_owner: "canonical.elmos.runner"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/30-incremental-regression-gate/SKILL.md` (`sha256:33d977773bc2e57dcd5a523aa3436f5f8297b257768d8a2b3991fc2602d6d8b6`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Incremental Regression Gate

Run impact-based regression after each wave so defects are caught before the final expensive full-suite gate.

## Trigger conditions
- wave integrated

## Inputs
- `impact map`
- `changed paths`
- `test catalog`

## Outputs
- `wave regression evidence`

## Procedure
1. Select tests by changed modules and dependency reach.
2. Always include previously failed related tests.
3. Track new failures to wave/task.
4. Block next dependent wave on unresolved regressions.

## Guardrails
- Do not rely solely on changed-file tests for high-centrality modules.

## Acceptance criteria
- wave passes selected regression set

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
