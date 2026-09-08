---
name: "elmos-architecture-invariant-ledger"
description: "Extract and track architectural, behavioral and operational invariants that must survive decomposition and integration."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/40-architecture-invariant-ledger/SKILL.md"
  source_sha256: "sha256:a4158041e4f3ea16b839bcb28a87ed2e6d1c881293fd24f747d2c8b90b7458c1"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "architecture_invariant_ledger"
  canonical_owner: "canonical.elmos.invariant-ledger"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/40-architecture-invariant-ledger/SKILL.md` (`sha256:a4158041e4f3ea16b839bcb28a87ed2e6d1c881293fd24f747d2c8b90b7458c1`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Architecture Invariant Ledger

Make cross-cutting invariants first-class planning objects.

## Inputs
- repository intelligence graph
- behavioral scenarios
- existing tests/contracts

## Outputs
- `invariant ledger`
- `owners`
- `proof obligations`
- `affected task links`

## Procedure
1. Extract invariants for API compatibility, transactions, security, auth, idempotency, ordering, data integrity, concurrency and deployment.
2. Classify each invariant as local, boundary or repository-global.
3. Bind invariant owners and proof mechanisms.
4. Attach invariants to every task/edge they constrain.
5. Prevent decomposition that leaves an invariant split across independently mergeable tasks without a joint gate.
6. Re-evaluate invariant coverage after every replan.

## Guardrails
- Global invariants cannot be discharged only by a leaf task's local unit test.

## Acceptance criteria
- all high-risk invariants have an owner and proof obligation
- no task plan can pass graph verification with unowned critical invariants

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
