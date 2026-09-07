---
name: "elmos-task-granularity-controller"
description: "Dynamically split or merge plan nodes using cohesion, coupling, context demand, uncertainty and verification distance."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/43-task-granularity-controller/SKILL.md"
  source_sha256: "sha256:c8e9ff9d3b0fa1567d90681cd277eb617e99ccb4757f8156b74b8ac6369e591b"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "task_granularity_controller"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/43-task-granularity-controller/SKILL.md` (`sha256:c8e9ff9d3b0fa1567d90681cd277eb617e99ccb4757f8156b74b8ac6369e591b`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Task Granularity Controller

Choose the cheapest safe unit of work rather than targeting a fixed task size.

## Inputs
- hierarchical node
- repository subgraph
- invariant links
- context estimate
- verifier availability

## Outputs
- `granularity score`
- `split/merge/keep decision`
- `rationale`

## Scoring dimensions
- context demand
- write surface
- semantic breadth
- cross-boundary coupling
- invariant density
- verification distance
- uncertainty

## Procedure
1. Compute normalized node complexity using `config/adaptive-decomposition-policy.yaml`.
2. Split nodes above threshold along the lowest-coupling semantic seam.
3. Merge nodes below threshold when separation adds more handoff cost than execution savings.
4. Force merge when splitting would sever a transaction or unmockable invariant.
5. Permit a larger task when verification is local and semantic cohesion is high.
6. Persist split/merge outcomes for telemetry learning.

## Guardrails
- Optimize completed-task cost and integration reliability, not number of tasks.

## Acceptance criteria
- every keep/split/merge decision is reproducible from recorded features

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
