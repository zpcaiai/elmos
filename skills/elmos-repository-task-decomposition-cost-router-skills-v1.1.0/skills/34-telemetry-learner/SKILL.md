---
name: elmos-telemetry-learner
version: 1.0.0
description: Learn actual Elmos cost/performance per model and task class so routing improves over time.
---

# Model Telemetry Learner

Learn actual Elmos cost/performance per model and task class so routing improves over time.

## Trigger conditions
- task/certification completion

## Inputs
- `execution records`
- `validation outcomes`
- `review defects`

## Outputs
- `updated model metrics`

## Procedure
1. Record first-pass success, total attempts, token/cost, latency, defect escape, integration conflict and task class.
2. Separate provider outages from model capability failures.
3. Update posterior after minimum sample thresholds.
4. Decay stale performance data.

## Guardrails
- Do not optimize solely for cheapness; retain quality and defect-escape metrics.

## Acceptance criteria
- metrics are auditable and task-class-specific

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
