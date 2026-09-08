---
name: elmos-change-impact-analyzer
version: 2.0.0
description: Estimate direct/transitive behavioral blast radius using scenarios, repository graph reachability, data-flow and confidence.
---

# Change Impact Analyzer v2

Estimate what can change and what must be revalidated, with uncertainty explicitly represented.

## Inputs
- `requirement/scenario graph`
- `repository intelligence graph`
- `invariant ledger`

## Outputs
- `impact subgraph`
- `direct/transitive impact sets`
- `risk triggers`
- `impact confidence`
- `candidate exploration tasks`

## Procedure
1. Trace each behavioral scenario through typed repository graph edges.
2. Separate write candidates from validation-only impact and runtime/deployment impact.
3. Expand through public contracts, data schemas, side effects and shared state until an evidence-backed cut set is reached.
4. Flag security/auth/transaction/concurrency/migration/public-API/global-config triggers.
5. Score confidence per impacted region based on graph evidence quality and unknown runtime edges.
6. If confidence is below policy threshold and consequences are meaningful, emit a bounded exploration task.
7. Produce test/build/observability surfaces for regression selection.

## Guardrails
- Conservative expansion is preferable to false certainty, but unexplained whole-repo impact is not acceptable.

## Acceptance criteria
- all acceptance scenarios have graph-backed impact paths
- uncertainty and cut-set reasons are recorded

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
