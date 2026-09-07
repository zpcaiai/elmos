# Implementation Guide — Database Schema Migration Planner

## Purpose

Plan expand/contract, online DDL, dependency order, backfill, validation, compatibility windows and reversible schema migrations.

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

1. Generate dependency-safe migration DAG
2. Classify blocking versus online operations
3. Plan expand/contract and backfill waves
4. Bind application compatibility windows
5. Produce rollback or compensating plan

## Native acceptance corpus

- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-01` — additive migration
- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-02` — destructive migration block
- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-03` — online index/build
- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-04` — large backfill resume
- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-05` — application dual-version window
- `ELMOS_DATABASE_SCHEMA_MIGRATION_PLANNER-06` — rollback after partial migration

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
