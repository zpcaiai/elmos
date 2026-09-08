---
name: elmos-retry-escalation-controller
version: 1.1.0
description: Bound retries and escalate intelligently instead of repeatedly spending on a model that has hit its capability limit.
---

# Retry & Escalation Controller

Bound retries and escalate intelligently instead of repeatedly spending on a model that has hit its capability limit.

## Trigger conditions
- classified failure

## Inputs
- `task`
- `attempt history`
- `router policy`
- `model_selection`

## Outputs
- `next attempt plan or terminal stop`

## Procedure
1. Retry same model only for allowed failure classes and attempt count.
2. Reuse cached context/evidence.
3. In Smart mode, on semantic/integration failure reroute at a higher eligible tier; architecture/long-horizon rules may promote as configured.
4. In manual `strict` mode, never change the primary implementation model; return `model_reselection_required` when another model is necessary.
5. In manual `smart_within_allowlist` mode, classify failure and ask the cost/performance router for the best eligible fallback from the same ten-model allowlist.
6. Record every fallback with from/to model, failure class, reason and incremental cost estimate.

## Guardrails
- Max total attempts enforced.
- Do not hide repeated failures.
- Never promote outside the hard allowlist or bypass a manual strict selection.

## Acceptance criteria
- next action follows policy and preserves attempt history

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
