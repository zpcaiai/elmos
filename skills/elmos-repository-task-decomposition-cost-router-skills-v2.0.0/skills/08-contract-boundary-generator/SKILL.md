---
name: elmos-contract-boundary-generator
version: 2.0.0
description: Create executable handoff contracts between tasks, including schemas, stubs, compatibility ranges and validators.
---

# Boundary Contract Generator v2

Turn cross-task assumptions into artifacts that can be validated before downstream execution.

## Inputs
- `tasks`
- `repository graph`
- `scenario graph`
- `invariant ledger`

## Outputs
- `interface/handoff contracts`
- `fixtures/stubs`
- `compatibility rules`
- `edge validators`

## Procedure
1. Specify produced/consumed artifacts, types/schemas, errors, invariants and lifecycle assumptions.
2. Prefer compile-time contracts, generated clients/types or schemas where available.
3. Generate stable fixtures/stubs only when they accurately model the contract.
4. Define backward/forward compatibility window for migrations and public APIs.
5. Bind every contract to a validator and affected scenarios.
6. Mark unstable contracts so scheduler prevents premature fan-out.

## Guardrails
- A prose handoff is not enough when a machine-checkable contract is possible.

## Acceptance criteria
- downstream task can start without hidden assumptions once incoming contracts validate

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
