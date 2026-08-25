---
name: "elmos-task-decomposer"
description: "Split the impacted work into low-complexity, independently testable tasks while preserving repository-level semantics."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/05-task-decomposer/SKILL.md"
  source_sha256: "sha256:4e9caec366f1d562c42b8938c6c3e0114adfe3c83fc81ecaf0858f274a1b681a"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "task_decomposer"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/05-task-decomposer/SKILL.md` (`sha256:4e9caec366f1d562c42b8938c6c3e0114adfe3c83fc81ecaf0858f274a1b681a`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Atomic Task Decomposer

Split the impacted work into low-complexity, independently testable tasks while preserving repository-level semantics.

## Trigger conditions
- impact map ready

## Inputs
- `requirement spec`
- `impact map`
- `architecture index`

## Outputs
- `atomic task candidates`

## Procedure
1. Prefer tasks that produce one coherent code/test/config outcome.
2. Keep each task within a small bounded write surface.
3. Separate contract changes from implementations when it enables safe parallelism.
4. Extract migrations and shared types before dependents.
5. Create explicit integration tasks where cross-module behavior cannot be validated locally.

## Guardrails
- Do not split transactional invariants across independently mergeable tasks.
- Do not split solely to make task count larger.

## Acceptance criteria
- each task has one objective
- each task has local acceptance evidence
- cross-task invariants explicitly represented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
