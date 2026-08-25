---
name: "elmos-complexity-estimator"
description: "Estimate implementation complexity separately from risk so routing can choose economical models without under-provisioning critical work."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/09-complexity-estimator/SKILL.md"
  source_sha256: "sha256:5df8822ba82f3a002271494acd286023679e6d8d7c4de3ba6798d8b620323db5"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "complexity_estimator"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/09-complexity-estimator/SKILL.md` (`sha256:5df8822ba82f3a002271494acd286023679e6d8d7c4de3ba6798d8b620323db5`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Complexity Estimator

Estimate implementation complexity separately from risk so routing can choose economical models without under-provisioning critical work.

## Trigger conditions
- before model routing

## Inputs
- `task`
- `repo profile`

## Outputs
- `complexity vector`
- `token/context estimate`

## Procedure
1. Score logic novelty, file count, dependency depth, test difficulty, tool use, context size and ambiguity.
2. Classify simple/standard/complex/long-horizon.
3. Estimate prompt/output tokens and expected tool cycles.

## Guardrails
- Never infer low risk solely from low LOC.

## Acceptance criteria
- complexity dimensions recorded with rationale

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
