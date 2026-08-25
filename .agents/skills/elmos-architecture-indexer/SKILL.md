---
name: "elmos-architecture-indexer"
description: "Build a compact architecture index optimized for downstream task planning and context slicing."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/03-architecture-indexer/SKILL.md"
  source_sha256: "sha256:e6643ee25fbc5800d976c6e514cad9d4bd974d518b0e769b8a48b2e07770638d"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "architecture_indexer"
  canonical_owner: "canonical.elmos.semantic-index"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/03-architecture-indexer/SKILL.md` (`sha256:e6643ee25fbc5800d976c6e514cad9d4bd974d518b0e769b8a48b2e07770638d`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Architecture Indexer

Build a compact architecture index optimized for downstream task planning and context slicing.

## Trigger conditions
- repo intake complete

## Inputs
- `repo profile`
- `source tree`

## Outputs
- `component index`
- `dependency edges`
- `entry-point map`
- `data-flow hints`

## Procedure
1. Identify public interfaces and module boundaries.
2. Map static dependency edges.
3. Identify persistence, messaging, external APIs and shared domain types.
4. Record high-centrality files and architectural invariants.

## Guardrails
- Prefer structural summaries over dumping entire files.

## Acceptance criteria
- major modules and cross-boundary dependencies represented

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
