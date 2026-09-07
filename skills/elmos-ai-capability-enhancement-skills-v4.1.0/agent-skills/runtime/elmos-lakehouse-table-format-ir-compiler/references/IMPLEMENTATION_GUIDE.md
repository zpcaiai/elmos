# Implementation Guide — Lakehouse Table Format IR Compiler

## Purpose

Compile snapshots, manifests, partition evolution, row-level deletes, schema evolution, transaction logs and reader/writer feature compatibility across Iceberg, Delta and Hudi.

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

1. model snapshot and commit semantics
2. represent schema and partition evolution
3. capture delete/update/merge features
4. negotiate reader/writer feature compatibility
5. preserve time travel and retention invariants

## Native acceptance corpus

- `ELMOS_LAKEHOUSE_TABLE_FORMAT_IR_COMPILER-01` — native scenario: model snapshot and commit semantics
- `ELMOS_LAKEHOUSE_TABLE_FORMAT_IR_COMPILER-02` — native scenario: represent schema and partition evolution
- `ELMOS_LAKEHOUSE_TABLE_FORMAT_IR_COMPILER-03` — native scenario: capture delete/update/merge features
- `ELMOS_LAKEHOUSE_TABLE_FORMAT_IR_COMPILER-04` — native scenario: negotiate reader/writer feature compatibility
- `ELMOS_LAKEHOUSE_TABLE_FORMAT_IR_COMPILER-05` — native scenario: preserve time travel and retention invariants

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
