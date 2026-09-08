---
name: "elmos-critical-path-resource-scheduler"
description: "Schedule the DAG using critical path, model/provider capacity, path locks, integration checkpoints and uncertainty."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/50-critical-path-resource-scheduler/SKILL.md"
  source_sha256: "sha256:3a6ca207223ba78e474051c0c18fe651800d2d804213cc7140cd49a83b66cc11"
  namespace: "repository-task-router-v2"
  runtime_module: "elmos_repository_orchestrator.runtime"
  runtime_callable: "dispatch"
  runtime_handler: "critical_path_resource_scheduler"
  canonical_owner: "canonical.elmos.execution-intelligence"
  implementation_state: "IMPLEMENTED"
  local_evidence: "NOT_RUN"
  external_evidence: "NOT_RUN"
  certification: "NOT_CERTIFIED"
---

## Repository runtime binding

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/50-critical-path-resource-scheduler/SKILL.md` (`sha256:3a6ca207223ba78e474051c0c18fe651800d2d804213cc7140cd49a83b66cc11`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Critical Path & Resource Scheduler

Optimize repository completion time without increasing merge risk.

## Inputs
- verified DAG
- task ETA/cost
- model/provider availability
- worktree/path locks
- integration checkpoints

## Outputs
- `execution waves`
- `critical path`
- `resource reservations`
- `speculative candidates`

## Procedure
1. Compute critical path using expected completed-task duration, not nominal model latency.
2. Parallelize only tasks with independent write ownership and validated incoming contracts.
3. Reserve scarce strong-model capacity for critical-path/high-risk work.
4. Permit speculative downstream work only with stable stubs and disposable worktrees.
5. Insert synchronization barriers around public contracts, migrations and global invariants.
6. Recompute schedule after replan or model/provider degradation.

## Acceptance criteria
- schedule is dependency-safe and resource-feasible
- concurrency choices have explicit integration-risk checks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
