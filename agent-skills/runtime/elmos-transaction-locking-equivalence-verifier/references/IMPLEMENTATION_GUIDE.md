# Implementation Guide — Transaction and Locking Equivalence Verifier

## Purpose

Verify isolation, lock acquisition, deadlock, savepoint, constraint timing, sequence visibility and concurrent business invariants across database engines.

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

1. Generate bounded concurrent schedules
2. Observe locks, waits and serialization failures
3. Compare commit/rollback and savepoint semantics
4. Verify business invariants under concurrency
5. Classify unavoidable engine-specific differences

## Native acceptance corpus

- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-01` — lost-update scenario
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-02` — write-skew scenario
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-03` — deadlock victim behavior
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-04` — savepoint rollback
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-05` — deferrable constraint timing
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-06` — sequence visibility
- `ELMOS_TRANSACTION_LOCKING_EQUIVALENCE_VERIFIER-07` — DDL transaction behavior

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
