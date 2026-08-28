# Implementation Guide — Data Retention, Archive and Tiering Controller

## Purpose

Compile retention, legal hold, hot/warm/cold tiering, archive verification and deletion propagation across databases, object stores, indexes, caches and backups.

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

1. translate policy into store-specific lifecycle rules
2. verify archive readability and integrity
3. propagate holds and deletion tombstones
4. prevent tiering from breaking query contracts
5. record disposal evidence and exceptions

## Native acceptance corpus

- `ELMOS_DATA_RETENTION_ARCHIVE_TIERING_CONTROLLER-01` — native scenario: translate policy into store-specific lifecycle rules
- `ELMOS_DATA_RETENTION_ARCHIVE_TIERING_CONTROLLER-02` — native scenario: verify archive readability and integrity
- `ELMOS_DATA_RETENTION_ARCHIVE_TIERING_CONTROLLER-03` — native scenario: propagate holds and deletion tombstones
- `ELMOS_DATA_RETENTION_ARCHIVE_TIERING_CONTROLLER-04` — native scenario: prevent tiering from breaking query contracts
- `ELMOS_DATA_RETENTION_ARCHIVE_TIERING_CONTROLLER-05` — native scenario: record disposal evidence and exceptions

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
