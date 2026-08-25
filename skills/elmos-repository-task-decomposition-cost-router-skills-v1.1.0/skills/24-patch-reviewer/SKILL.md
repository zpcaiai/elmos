---
name: elmos-patch-reviewer
version: 1.0.0
description: Apply model review only when expected defect reduction justifies the extra cost or policy requires a second model.
---

# Risk-Aware Patch Reviewer

Apply model review only when expected defect reduction justifies the extra cost or policy requires a second model.

## Trigger conditions
- local validation passes
- review trigger present

## Inputs
- `task`
- `diff`
- `evidence`
- `risk`

## Outputs
- `review findings`
- `approve/rework`

## Procedure
1. Check contract adherence, edge cases, security and repository conventions.
2. Use deterministic evidence as input.
3. Prefer reviewer from L3 for critical areas.
4. Avoid stylistic churn.

## Guardrails
- Reviewer cannot waive mandatory tests.

## Acceptance criteria
- findings are severity-ranked and actionable

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
