---
name: "elmos-adaptive-hierarchical-planner"
description: "Create a coarse-to-fine hierarchical plan and refine only branches whose complexity, uncertainty or readiness justify more detail."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/42-adaptive-hierarchical-planner/SKILL.md"
  source_sha256: "sha256:049e4ac8ad88fb05ea686f7b3827af62fd909184d1050005875f91e322635a69"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "adaptive_hierarchical_planner"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/42-adaptive-hierarchical-planner/SKILL.md` (`sha256:049e4ac8ad88fb05ea686f7b3827af62fd909184d1050005875f91e322635a69`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Adaptive Hierarchical Planner

Replace fixed-granularity decomposition with progressive refinement.

## Hierarchy
`goal -> capability -> changeset -> atomic_task -> microstep`

## Inputs
- requirement/scenario graph
- repository intelligence graph
- invariant ledger
- semantic seams
- impact map

## Outputs
- `hierarchical plan`
- `refinement frontier`
- `task candidates`
- `plan confidence`

## Procedure
1. Start with a small capability-level macro plan that covers all acceptance scenarios.
2. Refine only the next executable or high-risk branches; leave distant branches coarse.
3. At each refinement, minimize cross-boundary coupling while preserving scenario and invariant ownership.
4. Stop refinement when a node is independently executable, context-bounded and locally verifiable.
5. Allow microsteps only inside one worker context; do not schedule microsteps globally unless needed for recovery.
6. Recompute refinement frontier after execution evidence or repository discoveries.

## Guardrails
- Do not fully expand a large plan at run start merely for completeness.
- Do not make every node equally fine-grained.

## Acceptance criteria
- plan covers all scenarios without forced full-depth expansion
- every executable leaf satisfies the current granularity policy
- coarse nodes retain enough contract information for future refinement

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
