# Implementation Guide — Data Snapshot and CDC Controller

## Purpose

Execute initial snapshots, change data capture, ordering, deduplication, tombstones, gap detection and final reconciliation for database migration.

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

1. Create consistent snapshots with source position
2. Persist resumable CDC offsets and schema history
3. Deduplicate and order changes idempotently
4. Propagate deletes/tombstones
5. Detect gaps and block cutover

## Native acceptance corpus

- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-01` — consistent snapshot
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-02` — resume CDC after worker loss
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-03` — duplicate event idempotency
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-04` — out-of-order event handling
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-05` — delete propagation
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-06` — schema change during CDC
- `ELMOS_DATA_SNAPSHOT_CDC_CONTROLLER-07` — gap detection

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
