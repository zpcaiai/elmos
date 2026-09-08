---
name: elmos-budget-planner
version: 1.0.0
description: Allocate run budget across implementation, retries, integration and final certification before execution begins.
---

# Budget Planner

Allocate run budget across implementation, retries, integration and final certification before execution begins.

## Trigger conditions
- DAG + routing priors ready

## Inputs
- `DAG`
- `pricing/credits`
- `budget policy`

## Outputs
- `run budget plan`
- `per-wave budget`
- `reserve`

## Procedure
1. Estimate base cost per task.
2. Reserve escalation and final-certification budget.
3. Compute soft/hard stop thresholds.
4. Prioritize critical-path tasks when constrained.

## Guardrails
- Do not consume certification reserve for noncritical optional work without explicit policy.

## Acceptance criteria
- plan fits hard cap or run reports infeasible

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
