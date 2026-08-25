---
name: elmos-wave-scheduler
version: 1.0.0
description: Schedule ready DAG tasks to maximize throughput while honoring dependencies, path locks, quotas and model concurrency.
---

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
