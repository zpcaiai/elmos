# Implementation Guide — Dual-Write, Outbox and Saga Consistency Verifier

## Purpose

Verify atomic publication, outbox relay, inbox deduplication, saga compensation and cross-store business invariants during migration and steady-state operation.

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

1. prove or test database/outbox atomicity
2. verify relay ordering and deduplication
3. exercise compensation and irreversible steps
4. reconcile cross-store invariants
5. detect orphaned or ghost side effects

## Native acceptance corpus

- `ELMOS_DUAL_WRITE_OUTBOX_SAGA_CONSISTENCY_VERIFIER-01` — native scenario: prove or test database/outbox atomicity
- `ELMOS_DUAL_WRITE_OUTBOX_SAGA_CONSISTENCY_VERIFIER-02` — native scenario: verify relay ordering and deduplication
- `ELMOS_DUAL_WRITE_OUTBOX_SAGA_CONSISTENCY_VERIFIER-03` — native scenario: exercise compensation and irreversible steps
- `ELMOS_DUAL_WRITE_OUTBOX_SAGA_CONSISTENCY_VERIFIER-04` — native scenario: reconcile cross-store invariants
- `ELMOS_DUAL_WRITE_OUTBOX_SAGA_CONSISTENCY_VERIFIER-05` — native scenario: detect orphaned or ghost side effects

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
