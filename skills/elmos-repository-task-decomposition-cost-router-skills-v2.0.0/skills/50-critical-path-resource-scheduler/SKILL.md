---
name: elmos-critical-path-resource-scheduler
version: 2.0.0
description: Schedule the DAG using critical path, model/provider capacity, path locks, integration checkpoints and uncertainty.
---

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
