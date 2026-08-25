---
name: elmos-model-registry-guard
version: 1.1.0
description: Enforce the immutable set of ten allowed logical model aliases at planning, execution, retry and review time.
---

# Model Registry Guard

Enforce the immutable set of ten allowed logical model aliases at planning, execution, retry and review time.

## Trigger conditions
- any model selection

## Inputs
- `model alias`
- `registry`
- `model_selection`

## Outputs
- `allow/deny decision`

## Procedure
1. Resolve logical alias.
2. Verify alias is allowed by the run model-selection policy (Smart candidate, manual selected model, permitted fallback, or required verifier).
3. Verify enabled flag.
4. Hard fail unknown alias.
5. Record resolved provider ID and selection provenance in execution record.

## Guardrails
- No dynamic fallback to unregistered models.

## Acceptance criteria
- all executed model aliases belong to hard allowlist

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
