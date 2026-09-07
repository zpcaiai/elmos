---
name: elmos-atomicity-validator
version: 1.0.0
description: Reject over-large or dangerously over-split tasks and iterate decomposition until tasks are independently executable and verifiable.
---

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
