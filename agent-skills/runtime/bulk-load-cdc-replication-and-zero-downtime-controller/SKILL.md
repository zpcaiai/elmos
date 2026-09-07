---
name: bulk-load-cdc-replication-and-zero-downtime-controller
description: Govern consistent bulk load, log-based CDC, recoverable offsets, DDL synchronization, large transactions, replication conflicts, cutover frontiers, and reverse replication. Use for near-zero-downtime database migration, dual run, writer cutover, and rollback readiness.
---

# Bulk Load and CDC

## Bind the frontier

- Create a consistent snapshot and start CDC from the same authoritative source frontier.
- Record Oracle SCN, SQL Server LSN, MySQL binlog position or GTID, PostgreSQL LSN, or provider checkpoint; timestamps alone do not prove catch-up.
- Track chunk keys, partitions, counts, bytes, hashes, retries, and duration.
- Persist offsets durably and prove restart without gaps or duplicates.

## Control replication

- Select native logical replication, Debezium, GoldenGate, managed service, batch incremental, or an approved provider through a vendor-neutral contract.
- Declare DDL as auto-supported, manual apply, freeze, capture-and-approve, or unsupported.
- Observe transaction size, open duration, commit lag, spill, apply, and retry.
- For bidirectional paths, detect insert, update, delete/update, sequence, unique, and ordering conflicts.
- Count reverse replication as rollback only after testing reverse mappings, target-only data, new types/columns, triggers, sequences, and conflicts.

## Cut over safely

- Require load completion, healthy CDC, thresholded lag, reconciliation, DDL control, source-writer control, remaining-transaction apply, and an explicit frontier.
- Separate read cutover from authoritative write cutover.
- Return CUTOVER_READY, CUTOVER_READY_WITH_CONDITIONS, CUTOVER_BLOCKED, CUTOVER_IN_PROGRESS, CUTOVER_COMPLETED, or ROLLBACK_REQUIRED.
- Use Near-zero Downtime wording and block when unknown writers or unsupported CDC remain.
