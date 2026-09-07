---
name: "elmos-task-decomposer"
description: "Generate decomposition candidates from behavioral slices and semantic seams; final granularity is decided adaptively rather than by fixed atomic size."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/05-task-decomposer/SKILL.md"
  source_sha256: "sha256:246a2a06af16f383eaa193b5bf6076075b18e666eeee83094f291c3115b684bd"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/05-task-decomposer/SKILL.md` (`sha256:246a2a06af16f383eaa193b5bf6076075b18e666eeee83094f291c3115b684bd`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Semantic Task Decomposer v2

Generate candidate work units without assuming every task should be equally small.

## Inputs
- `hierarchical plan node`
- `scenario graph`
- `impact subgraph`
- `semantic seams`
- `invariant ledger`

## Outputs
- `candidate child nodes`
- `handoff candidates`
- `split rationale`

## Procedure
1. Decompose first by coherent behavioral/change responsibility, then map to code surfaces.
2. Prefer cuts at stable contracts, adapters, schema boundaries and locally verifiable seams.
3. Keep transaction, security, concurrency and tightly coupled state invariants inside one atomic unit unless a compatibility protocol creates a safe boundary.
4. Separate contract/migration preparation from dependents only when a validated handoff can unlock safe parallelism.
5. Create explicit integration/bridge tasks for behavior that cannot be proven by leaves.
6. Pass candidates to `elmos-task-granularity-controller`; do not enforce a fixed LOC/file/task-size target.

## Guardrails
- Do not split merely to maximize parallelism or cheap-model eligibility.
- Do not use directory boundaries as the sole evidence of task independence.

## Acceptance criteria
- each candidate has one coherent semantic outcome
- scenario/invariant ownership is explicit
- proposed seams have coupling evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
