---
name: elmos-run-state-journal
version: 1.0.0
description: Persist an append-only execution journal and materialized state snapshot for long-running repository jobs.
---

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
