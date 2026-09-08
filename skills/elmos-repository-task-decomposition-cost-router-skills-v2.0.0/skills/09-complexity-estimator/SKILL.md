---
name: elmos-complexity-estimator
version: 2.0.0
description: Estimate execution complexity, coordination complexity and uncertainty separately so planning and model routing can optimize completed-task cost.
---

# Complexity Estimator v2

Estimate both implementation difficulty and decomposition/coordination difficulty.

## Inputs
- `task or hierarchical node`
- `repository subgraph`
- `proof obligations`

## Outputs
- `execution complexity vector`
- `coordination complexity vector`
- `context/tool-cycle estimate`
- `uncertainty score`

## Procedure
1. Score logic novelty, algorithmic difficulty, context demand, tool use, test difficulty and expected edit/review loops.
2. Score cross-boundary coupling, number of handoffs, invariant density and integration sensitivity.
3. Estimate prompt/context/output footprint and expected completed-task duration.
4. Record confidence and evidence behind estimates.
5. Feed execution complexity to model router and coordination complexity to granularity/scheduler.

## Guardrails
- Low LOC/file count does not imply low complexity, risk or coordination cost.

## Acceptance criteria
- complexity and uncertainty are separate, evidence-backed dimensions

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
