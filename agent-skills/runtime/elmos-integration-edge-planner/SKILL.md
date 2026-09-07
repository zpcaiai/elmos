---
name: "elmos-integration-edge-planner"
description: "Plan validated handoffs and integration checkpoints at dependency edges so bad outputs cannot silently propagate downstream."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/47-integration-edge-planner/SKILL.md"
  source_sha256: "sha256:55070e66b989da48f4d75e0225a8709ed23e59abb94392a7abeb793f93a36b06"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "integration_edge_planner"
  canonical_owner: "canonical.elmos.contract-registry"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/47-integration-edge-planner/SKILL.md` (`sha256:55070e66b989da48f4d75e0225a8709ed23e59abb94392a7abeb793f93a36b06`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Integration Edge Planner

Treat dependency edges as executable contracts, not just arrows.

## Inputs
- task DAG
- boundary contracts
- proof obligations

## Outputs
- `edge handoff contracts`
- `edge validators`
- `integration checkpoints`

## Procedure
1. For each dependency edge, declare producer artifact, consumer expectation, compatibility range and verifier.
2. Place a checkpoint before fan-out from risky shared contracts.
3. Validate generated types, schemas, stubs and fixtures before unlocking downstream tasks.
4. Group tightly coupled edges into a boundary cluster with one integration gate.
5. Block propagation of failed or ambiguous handoffs.

## Guardrails
- A task status of `passed` does not unlock consumers until its outgoing handoffs are validated.

## Acceptance criteria
- every nontrivial edge has a machine-checkable or explicitly reviewed handoff

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
