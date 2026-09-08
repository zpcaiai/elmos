---
name: "elmos-task-dag-builder"
description: "Compile the current hierarchical plan frontier into a typed execution DAG with contracts, proof edges, locks and integration barriers."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/07-task-dag-builder/SKILL.md"
  source_sha256: "sha256:e991da35dd679a95bead058a779d74363077cb82a2d0a9a078eac16fbaf3f515"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "task_dag_builder"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/07-task-dag-builder/SKILL.md` (`sha256:e991da35dd679a95bead058a779d74363077cb82a2d0a9a078eac16fbaf3f515`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Typed Task DAG Builder v2

Compile executable leaves into a dependency graph whose edges carry semantics.

## Inputs
- `validated leaves`
- `hierarchical plan`
- `boundary contracts`
- `proof obligations`

## Outputs
- `typed DAG`
- `edge contracts`
- `path/resource locks`
- `integration barriers`
- `critical path seed`

## Procedure
1. Derive edges from artifact production/consumption, contract dependencies, data/schema ordering, path locks and proof prerequisites.
2. Type each edge (`data`, `contract`, `schema`, `build`, `runtime`, `verification`, `integration`).
3. Attach producer artifact, consumer expectation and edge validator.
4. Topologically sort and reject cycles or ambiguous ownership.
5. Insert integration barriers before unsafe fan-out and after high-risk shared changes.
6. Group ready nodes only after incoming handoffs are validated.
7. Pass graph to `elmos-plan-graph-verifier` before scheduling.

## Guardrails
- An arrow without a handoff contract is insufficient for nontrivial cross-task dependency.

## Acceptance criteria
- DAG is acyclic, typed, acceptance-complete and edge-validatable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
