# Implementation Guide — Online Schema Change and Backfill Controller

## Purpose

Execute expand/contract, online DDL, dual-read/write, throttled backfill, validation and cleanup without violating availability or data invariants.

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

1. compile expand/contract phases
2. throttle resumable backfills under SLO
3. verify dual-read/write compatibility
4. detect drift and repair missed rows
5. gate cleanup on mixed-version retirement

## Native acceptance corpus

- `ELMOS_ONLINE_SCHEMA_CHANGE_BACKFILL_CONTROLLER-01` — native scenario: compile expand/contract phases
- `ELMOS_ONLINE_SCHEMA_CHANGE_BACKFILL_CONTROLLER-02` — native scenario: throttle resumable backfills under SLO
- `ELMOS_ONLINE_SCHEMA_CHANGE_BACKFILL_CONTROLLER-03` — native scenario: verify dual-read/write compatibility
- `ELMOS_ONLINE_SCHEMA_CHANGE_BACKFILL_CONTROLLER-04` — native scenario: detect drift and repair missed rows
- `ELMOS_ONLINE_SCHEMA_CHANGE_BACKFILL_CONTROLLER-05` — native scenario: gate cleanup on mixed-version retirement

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
