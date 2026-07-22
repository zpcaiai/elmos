---
name: database-baseline-and-state-snapshot-controller
description: "Prepare isolated database seeds and comparable pre/post snapshots for Batch 9. Use when scenarios read or mutate relational, document or event-sourced state."
---

# Database Baseline and State Snapshot Controller

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Version schema, seed, logical data hash, sequences and excluded technical fields.
2. Capture stable ordered schema, row, column, constraint, sequence and logical transaction views.
3. Map generated IDs, timestamps and physical schema differences without losing references.

## Hard rules

- Use separate databases and never trigger business logic during snapshotting.
- Capture defaults, triggers and stored-procedure effects.
- Sanitize any production-derived seed.

## Output

Emit repeatable baseline manifests and read-only source/target snapshots.

