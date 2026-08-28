# Implementation Guide — Database Cutover and Rollback Certifier

## Purpose

Certify snapshot/CDC reconciliation, write freeze or dual-write, final cutover, rollback window and source retirement with no unexplained data loss.

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

1. Freeze exact source/target positions
2. Require zero unexplained reconciliation differences
3. Exercise application cutover and rollback
4. Set rollback data capture strategy
5. Retire source only after expiry and acceptance

## Native acceptance corpus

- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-01` — final CDC catch-up
- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-02` — zero-gap reconciliation
- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-03` — read/write cutover
- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-04` — rollback with new writes
- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-05` — DNS/connection failover
- `ELMOS_DATABASE_CUTOVER_ROLLBACK_CERTIFIER-06` — source retirement gate

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
