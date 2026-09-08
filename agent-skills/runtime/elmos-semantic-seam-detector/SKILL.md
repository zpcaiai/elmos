---
name: "elmos-semantic-seam-detector"
description: "Find safe decomposition boundaries using architecture seams, contracts, ownership, data-flow cuts and verification locality."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/41-semantic-seam-detector/SKILL.md"
  source_sha256: "sha256:c124ac8f6f4b403a0418241ee90d979cf320b969e80e933eacced90563fd1354"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "semantic_seam_detector"
  canonical_owner: "canonical.elmos.impact-graph"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/41-semantic-seam-detector/SKILL.md` (`sha256:c124ac8f6f4b403a0418241ee90d979cf320b969e80e933eacced90563fd1354`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Semantic Seam Detector

Find boundaries where work can be split with minimal coordination cost.

## Inputs
- repository intelligence graph
- invariant ledger
- scenario graph

## Outputs
- `candidate seams`
- `unsafe seams`
- `coupling score`
- `recommended change clusters`

## Procedure
1. Locate explicit interfaces, modules, adapters, ports, schemas, generated clients and testable boundaries.
2. Penalize cuts through transactions, shared mutable state, tightly coupled call/data cycles and migration compatibility windows.
3. Score seams by semantic cohesion, cross-edge count, contract stability and verification locality.
4. Identify bridge seams where a stub/fixture can unlock safe parallelism.
5. Feed recommended clusters into hierarchical planner and granularity controller.

## Guardrails
- A directory boundary is not automatically a semantic seam.

## Acceptance criteria
- proposed split points minimize hidden cross-task assumptions
- unsafe splits carry explicit reasons

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
