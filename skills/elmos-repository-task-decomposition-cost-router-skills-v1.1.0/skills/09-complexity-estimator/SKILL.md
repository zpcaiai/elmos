---
name: elmos-complexity-estimator
version: 1.0.0
description: Estimate implementation complexity separately from risk so routing can choose economical models without under-provisioning critical work.
---

# Complexity Estimator

Estimate implementation complexity separately from risk so routing can choose economical models without under-provisioning critical work.

## Trigger conditions
- before model routing

## Inputs
- `task`
- `repo profile`

## Outputs
- `complexity vector`
- `token/context estimate`

## Procedure
1. Score logic novelty, file count, dependency depth, test difficulty, tool use, context size and ambiguity.
2. Classify simple/standard/complex/long-horizon.
3. Estimate prompt/output tokens and expected tool cycles.

## Guardrails
- Never infer low risk solely from low LOC.

## Acceptance criteria
- complexity dimensions recorded with rationale

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
