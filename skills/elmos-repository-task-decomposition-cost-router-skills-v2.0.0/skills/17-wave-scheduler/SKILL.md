---
name: elmos-wave-scheduler
version: 2.0.0
description: Dispatch dependency-safe work using the critical-path/resource scheduler and validated handoffs rather than simple ready-node waves.
---

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
