---
name: "elmos-run-state-journal"
description: "Persist an append-only execution journal and materialized state snapshot for long-running repository jobs."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/33-run-state-journal/SKILL.md"
  source_sha256: "sha256:de0cc96f5f0b268551a53b46b4422d84b790119c808b367879f1b1e517a682f4"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "run_state_journal"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/33-run-state-journal/SKILL.md` (`sha256:de0cc96f5f0b268551a53b46b4422d84b790119c808b367879f1b1e517a682f4`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Run State Journal

Persist an append-only execution journal and materialized state snapshot for long-running repository jobs.

## Trigger conditions
- every state transition

## Inputs
- `run/task event`

## Outputs
- `event log`
- `state snapshot`

## Procedure
1. Append timestamped event.
2. Update materialized task/DAG status atomically.
3. Persist model usage, cost, ETA and evidence references.
4. Checkpoint after every worker and integration action.

## Guardrails
- Journal must be durable before acknowledging completion of a step.

## Acceptance criteria
- run can be reconstructed from journal + repository

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
