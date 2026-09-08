---
name: elmos-incremental-regression-gate
version: 2.0.0
description: Run graph/scenario-based regression after each integration checkpoint and use unexpected failures as impact-model feedback.
---

# Incremental Regression Gate v2

Detect incorrect impact assumptions as early as possible.

## Inputs
- `repository graph delta`
- `scenario graph`
- `changed paths/symbols`
- `baseline evidence`
- `test catalog`

## Outputs
- `checkpoint regression evidence`
- `unexpected-impact findings`

## Procedure
1. Select tests from changed nodes, typed dependency reach and affected scenarios.
2. Include baseline comparison and previously failing related tests.
3. Add contract/invariant-specific probes for high-risk boundaries.
4. Attribute failures to integration checkpoint/task where evidence permits.
5. When a failure occurs outside predicted impact, update RIG/impact confidence and trigger local replan.
6. Block downstream dependent work on unresolved regressions.

## Guardrails
- High-centrality or global-invariant changes require broader regression than changed-file selection.

## Acceptance criteria
- checkpoint passes its graph-derived regression/proof set

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
