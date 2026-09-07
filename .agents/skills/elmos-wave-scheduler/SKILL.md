---
name: "elmos-wave-scheduler"
description: "Dispatch dependency-safe work using the critical-path/resource scheduler and validated handoffs rather than simple ready-node waves."
metadata:
  package: "elmos-repository-task-decomposition-cost-router-skills"
  package_version: "2.0.0"
  source_version: "2.0.0"
  source_path: "skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/17-wave-scheduler/SKILL.md"
  source_sha256: "sha256:d76765994c857c39ae121af18172ad6503953483ec0fc9591524e5ec24aa3510"
  namespace: "repository-task-router-v2"
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

- Immutable package source: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/skills/17-wave-scheduler/SKILL.md` (`sha256:d76765994c857c39ae121af18172ad6503953483ec0fc9591524e5ec24aa3510`).
- Shared source policy and schemas: `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/config/` and `skills/elmos-repository-task-decomposition-cost-router-skills-v2.0.0/schemas/`.
- Repository-corrected contracts and the exact 54-node DAG: `docs/repository-task-router-skills/compiled-schemas/` and `docs/repository-task-router-skills/dependency-dag.json`.
- Bounded dispatch binding: `elmos_repository_orchestrator.runtime:dispatch`; implementation state is `IMPLEMENTED` and local execution evidence is `NOT_RUN`.
- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.
- Provider/SCM/worktree external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.

## Immutable package guidance
# Adaptive Wave Scheduler v2

Schedule work to minimize repository completion time under model, provider, path-lock and integration constraints.

## Inputs
- `verified typed DAG`
- `critical path/resource plan`
- `model quotas`
- `budget`

## Outputs
- `execution wave plan`
- `dispatch rationale`

## Procedure
1. Select nodes whose dependencies **and incoming handoff validators** have passed.
2. Exclude overlapping write/resource ownership and unstable shared contracts.
3. Prioritize critical-path nodes using expected completed duration.
4. Reserve strong-model capacity for risk/complexity where it has highest expected value.
5. Allow speculative parallelism only behind stable stubs in disposable worktrees.
6. Insert synchronization barriers required by integration-edge planner.
7. Recompute schedule after replans, quota shifts or provider degradation.

## Guardrails
- No dependency, contract, lock or barrier violation for throughput.

## Acceptance criteria
- every dispatch is graph-ready, handoff-ready and resource-safe

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
