---
name: elmos-incremental-regression-gate
version: 1.0.0
description: Run impact-based regression after each wave so defects are caught before the final expensive full-suite gate.
---

# Incremental Regression Gate

Run impact-based regression after each wave so defects are caught before the final expensive full-suite gate.

## Trigger conditions
- wave integrated

## Inputs
- `impact map`
- `changed paths`
- `test catalog`

## Outputs
- `wave regression evidence`

## Procedure
1. Select tests by changed modules and dependency reach.
2. Always include previously failed related tests.
3. Track new failures to wave/task.
4. Block next dependent wave on unresolved regressions.

## Guardrails
- Do not rely solely on changed-file tests for high-centrality modules.

## Acceptance criteria
- wave passes selected regression set

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
