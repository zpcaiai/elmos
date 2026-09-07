---
name: elmos-task-decomposer
version: 2.0.0
description: Generate decomposition candidates from behavioral slices and semantic seams; final granularity is decided adaptively rather than by fixed atomic size.
---

# Semantic Task Decomposer v2

Generate candidate work units without assuming every task should be equally small.

## Inputs
- `hierarchical plan node`
- `scenario graph`
- `impact subgraph`
- `semantic seams`
- `invariant ledger`

## Outputs
- `candidate child nodes`
- `handoff candidates`
- `split rationale`

## Procedure
1. Decompose first by coherent behavioral/change responsibility, then map to code surfaces.
2. Prefer cuts at stable contracts, adapters, schema boundaries and locally verifiable seams.
3. Keep transaction, security, concurrency and tightly coupled state invariants inside one atomic unit unless a compatibility protocol creates a safe boundary.
4. Separate contract/migration preparation from dependents only when a validated handoff can unlock safe parallelism.
5. Create explicit integration/bridge tasks for behavior that cannot be proven by leaves.
6. Pass candidates to `elmos-task-granularity-controller`; do not enforce a fixed LOC/file/task-size target.

## Guardrails
- Do not split merely to maximize parallelism or cheap-model eligibility.
- Do not use directory boundaries as the sole evidence of task independence.

## Acceptance criteria
- each candidate has one coherent semantic outcome
- scenario/invariant ownership is explicit
- proposed seams have coupling evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
