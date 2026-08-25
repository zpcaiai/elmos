---
name: "elmos-atomicity-validator"
description: "Reject over-large or dangerously over-split tasks and iterate decomposition until tasks are independently executable and verifiable."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/06-atomicity-validator/SKILL.md"
  source_sha256: "sha256:f7e495f04d0fe0c0794b774e71319831cc12bd035f4ec2c97a021a5caf2b9e36"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "atomicity_validator"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/06-atomicity-validator/SKILL.md` (`sha256:f7e495f04d0fe0c0794b774e71319831cc12bd035f4ec2c97a021a5caf2b9e36`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Atomicity Validator

Reject over-large or dangerously over-split tasks and iterate decomposition until tasks are independently executable and verifiable.

## Trigger conditions
- task candidates created

## Inputs
- `atomic tasks`
- `impact map`

## Outputs
- `validated task set`
- `split/merge recommendations`

## Procedure
1. Score write-surface size, semantic cohesion, context demand and acceptance-test locality.
2. Split tasks exceeding configurable complexity threshold.
3. Merge tasks whose separation creates hidden invariants or excessive coordination.
4. Require owned/read/forbidden paths for every task.

## Guardrails
- Security, transaction, concurrency and schema invariants may force larger atomic units.

## Acceptance criteria
- no task violates atomicity thresholds without explicit reason

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
