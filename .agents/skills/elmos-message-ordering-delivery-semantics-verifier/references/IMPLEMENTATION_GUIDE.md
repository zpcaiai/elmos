# Implementation Guide — Message Ordering and Delivery Semantics Verifier

## Purpose

Verify at-most-once, at-least-once, effectively-once, partition ordering, redelivery, dead-letter and backpressure behavior.

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

1. inject duplicate, delayed and reordered messages
2. verify partition-key and causal ordering
3. exercise acknowledgment and redelivery windows
4. validate DLQ/retry and poison-message handling
5. measure backpressure and consumer recovery

## Native acceptance corpus

- `ELMOS_MESSAGE_ORDERING_DELIVERY_SEMANTICS_VERIFIER-01` — native scenario: inject duplicate, delayed and reordered messages
- `ELMOS_MESSAGE_ORDERING_DELIVERY_SEMANTICS_VERIFIER-02` — native scenario: verify partition-key and causal ordering
- `ELMOS_MESSAGE_ORDERING_DELIVERY_SEMANTICS_VERIFIER-03` — native scenario: exercise acknowledgment and redelivery windows
- `ELMOS_MESSAGE_ORDERING_DELIVERY_SEMANTICS_VERIFIER-04` — native scenario: validate DLQ/retry and poison-message handling
- `ELMOS_MESSAGE_ORDERING_DELIVERY_SEMANTICS_VERIFIER-05` — native scenario: measure backpressure and consumer recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
