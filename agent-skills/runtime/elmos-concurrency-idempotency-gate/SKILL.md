---
name: "elmos-concurrency-idempotency-gate"
description: "Validate race safety, retries, duplicate delivery and side-effect idempotency for concurrent/distributed changes."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/27-concurrency-idempotency-gate/SKILL.md"
  source_sha256: "sha256:5d6d2267040a8f1a46f710dd68388f830c082ce5434d44fcb70719ea3fd03346"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "concurrency_idempotency_gate"
  canonical_owner: "canonical.elmos.verification-fabric"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/27-concurrency-idempotency-gate/SKILL.md` (`sha256:5d6d2267040a8f1a46f710dd68388f830c082ce5434d44fcb70719ea3fd03346`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Concurrency & Idempotency Gate

Validate race safety, retries, duplicate delivery and side-effect idempotency for concurrent/distributed changes.

## Trigger conditions
- concurrency/queue/job/payment-like side effects

## Inputs
- `implementation`
- `tests`
- `state model`

## Outputs
- `stress/race/idempotency evidence`

## Procedure
1. Identify shared state and retry boundaries.
2. Run race/stress/replay tests where possible.
3. Check idempotency keys/transactions/locks.
4. Simulate duplicate and out-of-order events.

## Guardrails
- Promote to L3 when semantics are uncertain.

## Acceptance criteria
- no known duplicate side effect or race under tested scenarios

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
