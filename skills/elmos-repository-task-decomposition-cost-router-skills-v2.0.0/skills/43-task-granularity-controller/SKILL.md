---
name: elmos-task-granularity-controller
version: 2.0.0
description: Dynamically split or merge plan nodes using cohesion, coupling, context demand, uncertainty and verification distance.
---

# Task Granularity Controller

Choose the cheapest safe unit of work rather than targeting a fixed task size.

## Inputs
- hierarchical node
- repository subgraph
- invariant links
- context estimate
- verifier availability

## Outputs
- `granularity score`
- `split/merge/keep decision`
- `rationale`

## Scoring dimensions
- context demand
- write surface
- semantic breadth
- cross-boundary coupling
- invariant density
- verification distance
- uncertainty

## Procedure
1. Compute normalized node complexity using `config/adaptive-decomposition-policy.yaml`.
2. Split nodes above threshold along the lowest-coupling semantic seam.
3. Merge nodes below threshold when separation adds more handoff cost than execution savings.
4. Force merge when splitting would sever a transaction or unmockable invariant.
5. Permit a larger task when verification is local and semantic cohesion is high.
6. Persist split/merge outcomes for telemetry learning.

## Guardrails
- Optimize completed-task cost and integration reliability, not number of tasks.

## Acceptance criteria
- every keep/split/merge decision is reproducible from recorded features

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
