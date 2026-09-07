---
name: elmos-risk-classifier
version: 2.0.0
description: Classify semantic consequence, rollback difficulty and blast radius independently from task size and complexity.
---

# Risk Classifier v2

Classify how costly it would be for a locally plausible patch to be wrong.

## Inputs
- `task`
- `impact subgraph`
- `invariant ledger`

## Outputs
- `risk vector`
- `minimum model/review tier`
- `mandatory proof obligations/gates`

## Procedure
1. Evaluate security, privacy, authn/authz and secrets boundaries.
2. Evaluate irreversible state/data mutations and migration compatibility.
3. Evaluate concurrency, idempotency, ordering and distributed side effects.
4. Evaluate public API/schema compatibility and downstream ecosystem blast radius.
5. Evaluate rollback complexity, observability gaps and deployment coupling.
6. Promote verification/model tier independently of task granularity.

## Guardrails
- Cost pressure cannot downgrade mandatory safety/compatibility gates.

## Acceptance criteria
- risk consequences, required gates and rollback expectations are explicit

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
