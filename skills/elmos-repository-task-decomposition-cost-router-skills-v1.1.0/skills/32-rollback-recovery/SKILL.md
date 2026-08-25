---
name: elmos-rollback-recovery
version: 1.0.0
description: Recover from integration failures or interrupted sessions without losing validated work.
---

# Rollback & Recovery Manager

Recover from integration failures or interrupted sessions without losing validated work.

## Trigger conditions
- run interruption
- bad integration
- provider/network failure

## Inputs
- `run journal`
- `task branches`
- `integration log`

## Outputs
- `resumed state or rollback state`

## Procedure
1. Reconstruct state from durable journal.
2. Reuse passed tasks and cached context.
3. Rollback only integration commits attributable to failed wave.
4. Requeue unfinished tasks.
5. Verify repository integrity before resume.

## Guardrails
- Never discard unrelated user changes.

## Acceptance criteria
- resume point deterministic and repository consistent

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
