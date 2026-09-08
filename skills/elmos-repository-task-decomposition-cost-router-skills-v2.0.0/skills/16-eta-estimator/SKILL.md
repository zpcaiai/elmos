---
name: elmos-eta-estimator
version: 1.0.0
description: Estimate machine wall-clock completion time for the Elmos run and update ETA from observed execution durations.
---

# Autonomous ETA Estimator

Estimate machine wall-clock completion time for the Elmos run and update ETA from observed execution durations.

## Trigger conditions
- DAG and model routes known

## Inputs
- `task durations priors`
- `concurrency`
- `critical path`

## Outputs
- `P50/P90 autonomous ETA`
- `optional human-effort comparison`

## Procedure
1. Estimate per-task tool/model duration.
2. Compute wave and critical-path runtime under concurrency limits.
3. Update posterior after every completed wave.
4. Report autonomous wall-clock separately from human comparison.

## Guardrails
- Never substitute person-days for system runtime ETA.

## Acceptance criteria
- ETA includes confidence range and dominant critical-path tasks

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
