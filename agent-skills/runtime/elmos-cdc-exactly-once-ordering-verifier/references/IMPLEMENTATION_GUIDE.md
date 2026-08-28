# Implementation Guide — CDC Exactly-Once and Ordering Verifier

## Purpose

Verify source log capture, snapshot boundary, schema change, ordering, deduplication, tombstone and offset recovery for CDC pipelines.

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

1. align snapshot and log positions
2. inject duplicate, late and out-of-order events
3. verify DDL and schema-change handling
4. recover offsets after connector failure
5. reconcile deletes and tombstones

## Native acceptance corpus

- `ELMOS_CDC_EXACTLY_ONCE_ORDERING_VERIFIER-01` — native scenario: align snapshot and log positions
- `ELMOS_CDC_EXACTLY_ONCE_ORDERING_VERIFIER-02` — native scenario: inject duplicate, late and out-of-order events
- `ELMOS_CDC_EXACTLY_ONCE_ORDERING_VERIFIER-03` — native scenario: verify DDL and schema-change handling
- `ELMOS_CDC_EXACTLY_ONCE_ORDERING_VERIFIER-04` — native scenario: recover offsets after connector failure
- `ELMOS_CDC_EXACTLY_ONCE_ORDERING_VERIFIER-05` — native scenario: reconcile deletes and tombstones

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
