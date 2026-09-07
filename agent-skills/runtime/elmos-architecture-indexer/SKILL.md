---
name: "elmos-architecture-indexer"
description: "Produce a compact architecture view and seed the evidence-backed Repository Intelligence Graph used by adaptive planning."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/03-architecture-indexer/SKILL.md"
  source_sha256: "sha256:efac599dbf286ccc97cecbd1e806c87cbdf408b1ed5f31adbfa30273f87aac85"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/03-architecture-indexer/SKILL.md` (`sha256:efac599dbf286ccc97cecbd1e806c87cbdf408b1ed5f31adbfa30273f87aac85`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Architecture Indexer v2

Recover the repository's architectural language before task decomposition.

## Inputs
- `repo profile`
- `source/build/test tree`

## Outputs
- `component index`
- `entry-point map`
- `architecture conventions`
- `RIG seed`

## Procedure
1. Identify modules, boundaries, public interfaces, adapters, domain cores and generated surfaces.
2. Recover build/test entry points, deployable units and package-manager/build-tool relationships.
3. Identify persistence, messaging, external APIs, shared domain types and config surfaces.
4. Record architecture conventions from sibling implementations and repeated patterns.
5. Mark high-centrality nodes, ownership ambiguity and suspected architectural seams.
6. Delegate full typed graph construction to `elmos-repository-intelligence-graph`.

## Guardrails
- Prefer structural summaries and exact evidence pointers over large source dumps.

## Acceptance criteria
- major modules and build/test/runtime boundaries are represented
- downstream RIG construction has evidence anchors

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
