---
name: progressive-traffic-shift-and-canary-controller
description: Evaluate staged traffic-shift and canary gates across technical, data, contract, security, and business evidence. Use after shadow validation and before any production routing change.
---

# Progressive Traffic Shift and Canary Controller

## Workflow

1. Bind the request to a provider, current/requested stage, cohort, landscape version, artifact set, and rollback plan.
2. Progress through shadow-only, internal, 1%, 5%, 10%, 25%, 50%, and full traffic using deterministic cohorts.
3. Evaluate provider health, availability, error, latency, business invariants, data consistency, contracts, security, message/CDC lag, retry/idempotency, session compatibility, unknown consumers, and rollback evidence.
4. Roll back or hold on business failure even when technical SLOs pass.
5. Pause when the provider is unhealthy; hold on any other gate failure.
6. Require human approval for full traffic, production write ownership, or irreversible operations. Never let an agent mutate a provider or auto-promote production writes.

## Output

Return `PROMOTE`, `HOLD`, `PAUSE`, `ROLLBACK`, or `HUMAN_REVIEW`, the effective unchanged/promoted stage, blockers, and evidence references.
