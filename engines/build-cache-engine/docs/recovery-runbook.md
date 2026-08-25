# Failure and Recovery Runbook

## Service restart

1. Stop scheduling new work.
2. Load active runs and compare materialized state with journal sequences.
3. Mark expired `RUNNING` nodes `RECOVERING`; increment lease epoch on claim.
4. Inspect staged files by state.
5. Validate newest compatible checkpoint.
6. Resume promotion, tree assembly, or node execution.
7. Verify published pointer before declaring recovery complete.

## Disk full

1. Reject new reservations.
2. Preserve metadata, journal, sealed artifacts, checkpoints, and active publish trees.
3. Delete disposable scratch and unreferenced pending temporary files.
4. Run project-scoped GC dry-run, then approved GC.
5. Resume only after free-space and quota thresholds pass.

## Corrupt local CAS object

1. Mark object quarantined.
2. Block trusted consumers.
3. Attempt repair from verified remote replica.
4. Recompute if repair is unavailable.
5. Revalidate dependent Action Cache entries and certificates.

## Remote outage

1. Continue local execution when policy permits.
2. Queue bounded write-behind uploads.
3. Avoid repeated transfer storms through backoff.
4. Synchronize later using digest-addressed create-if-absent.
5. Publish remote metadata only after referenced objects are durable.

## Stale worker

1. Increment lease epoch on recovery claim.
2. Reject every later commit from the old epoch.
3. Inspect pending files; quarantine or delete incomplete bytes.
4. Reuse only sealed, verified artifacts.
