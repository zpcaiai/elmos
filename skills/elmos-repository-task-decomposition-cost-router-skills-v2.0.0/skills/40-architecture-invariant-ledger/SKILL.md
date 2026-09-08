---
name: elmos-architecture-invariant-ledger
version: 2.0.0
description: Extract and track architectural, behavioral and operational invariants that must survive decomposition and integration.
---

# Architecture Invariant Ledger

Make cross-cutting invariants first-class planning objects.

## Inputs
- repository intelligence graph
- behavioral scenarios
- existing tests/contracts

## Outputs
- `invariant ledger`
- `owners`
- `proof obligations`
- `affected task links`

## Procedure
1. Extract invariants for API compatibility, transactions, security, auth, idempotency, ordering, data integrity, concurrency and deployment.
2. Classify each invariant as local, boundary or repository-global.
3. Bind invariant owners and proof mechanisms.
4. Attach invariants to every task/edge they constrain.
5. Prevent decomposition that leaves an invariant split across independently mergeable tasks without a joint gate.
6. Re-evaluate invariant coverage after every replan.

## Guardrails
- Global invariants cannot be discharged only by a leaf task's local unit test.

## Acceptance criteria
- all high-risk invariants have an owner and proof obligation
- no task plan can pass graph verification with unowned critical invariants

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
