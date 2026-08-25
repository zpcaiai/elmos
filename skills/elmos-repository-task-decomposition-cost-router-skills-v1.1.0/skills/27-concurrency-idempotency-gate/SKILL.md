---
name: elmos-concurrency-idempotency-gate
version: 1.0.0
description: Validate race safety, retries, duplicate delivery and side-effect idempotency for concurrent/distributed changes.
---

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
