# Implementation Guide — API Consumer-Driven Contract Verifier

## Purpose

Generate and execute provider/consumer contracts for APIs, tools and events, including version negotiation, errors, auth and deployment compatibility.

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

1. mine real consumer expectations
2. publish versioned contract artifacts
3. verify provider against all active consumers
4. test mixed-version deployment and rollback
5. detect orphaned and shadow consumers

## Native acceptance corpus

- `ELMOS_API_CONSUMER_DRIVEN_CONTRACT_VERIFIER-01` — native scenario: mine real consumer expectations
- `ELMOS_API_CONSUMER_DRIVEN_CONTRACT_VERIFIER-02` — native scenario: publish versioned contract artifacts
- `ELMOS_API_CONSUMER_DRIVEN_CONTRACT_VERIFIER-03` — native scenario: verify provider against all active consumers
- `ELMOS_API_CONSUMER_DRIVEN_CONTRACT_VERIFIER-04` — native scenario: test mixed-version deployment and rollback
- `ELMOS_API_CONSUMER_DRIVEN_CONTRACT_VERIFIER-05` — native scenario: detect orphaned and shadow consumers

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
