# Implementation Guide — Webhook Delivery Security and Reliability Controller

## Purpose

Generate and verify webhook signing, replay protection, delivery retries, ordering, endpoint rotation, observability and dead-letter handling.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. generate canonical signature and timestamp verification
2. enforce replay and tenant isolation
3. implement retry and idempotent receipt
4. rotate endpoints and secrets safely
5. certify delivery and reconciliation evidence

## Native acceptance corpus

- `ELMOS_WEBHOOK_DELIVERY_SECURITY_RELIABILITY_CONTROLLER-01` — native scenario: generate canonical signature and timestamp verification
- `ELMOS_WEBHOOK_DELIVERY_SECURITY_RELIABILITY_CONTROLLER-02` — native scenario: enforce replay and tenant isolation
- `ELMOS_WEBHOOK_DELIVERY_SECURITY_RELIABILITY_CONTROLLER-03` — native scenario: implement retry and idempotent receipt
- `ELMOS_WEBHOOK_DELIVERY_SECURITY_RELIABILITY_CONTROLLER-04` — native scenario: rotate endpoints and secrets safely
- `ELMOS_WEBHOOK_DELIVERY_SECURITY_RELIABILITY_CONTROLLER-05` — native scenario: certify delivery and reconciliation evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
