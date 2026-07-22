---
name: data-backfill-reconciliation-and-cutover-validator
description: Validate resumable backfill, CDC catch-up, reconciliation, cutover frontier, and separate read/write gates. Use before changing data reads or authoritative writes.
---

# Data Backfill, Reconciliation, and Cutover Validator

## Workflow

1. Partition backfill deterministically and record bounds, checkpoints, source/target counts and hashes, rejected records, and idempotent upsert proof.
2. Resume from durable checkpoints; never restart ambiguously or conceal rejected records.
3. Validate CDC source/applied positions, time/record/transaction lag, retry/error queues, health, and resumability.
4. Reconcile structure, partition hashes, aggregates, domain invariants, and sampled records.
5. Freeze an auditable cutover frontier and verify target performance, consumers, rollback, and cleanup.
6. Permit read cutover only after backfill, CDC, reconciliation, performance, consumer, and frontier gates pass.
7. Permit write cutover only after read gates plus rollback readiness, new-write idempotency, and business-owner approval.

## Failure behavior

Any missing checkpoint, hash mismatch, reject, lag, reconciliation difference, or evidence gap keeps legacy primary and returns exact blockers.
