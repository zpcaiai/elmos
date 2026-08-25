---
name: "elmos-wave-scheduler"
description: "Schedule ready DAG tasks to maximize throughput while honoring dependencies, path locks, quotas and model concurrency."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "1.1.0"
  source_version: "1.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/17-wave-scheduler/SKILL.md"
  source_sha256: "sha256:3ffec64f45bca31e1311fab3c41f16bc2e06d3fc89bc89d1cd40788618445f90"
  namespace: "repository-task-router-v1"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "wave_scheduler"
  canonical_owner: "canonical.elmos.durable-runtime"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/skills/17-wave-scheduler/SKILL.md` (`sha256:3ffec64f45bca31e1311fab3c41f16bc2e06d3fc89bc89d1cd40788618445f90`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v1.1.0/schemas/`.
- Repository-corrected contracts and the exact 37-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Parallel Wave Scheduler

Schedule ready DAG tasks to maximize throughput while honoring dependencies, path locks, quotas and model concurrency.

## Trigger conditions
- DAG ready

## Inputs
- `DAG`
- `path locks`
- `model quotas`
- `budget`

## Outputs
- `execution wave plan`

## Procedure
1. Select ready tasks.
2. Exclude overlapping write ownership.
3. Respect provider concurrency and budget.
4. Prefer critical-path acceleration when cost increase stays within policy.
5. Persist dispatch order.

## Guardrails
- No dependency violation.
- No concurrent overlapping writes.

## Acceptance criteria
- every dispatched task is ready and lock-safe

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
