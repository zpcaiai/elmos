# Implementation Guide — SQL Catalog IR Compiler

## Purpose

Compile catalogs, schemas, tables, types, defaults, generated values, constraints, indexes, partitions, views, roles, grants and RLS into DB-SIR.

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

1. Parse vendor-native DDL and metadata
2. Preserve object identity and dependency order
3. Model generated/identity/sequence semantics
4. Capture grants, roles and row security
5. Record opaque extensions and unsupported constructs

## Native acceptance corpus

- `ELMOS_SQL_CATALOG_IR_COMPILER-01` — tables/constraints/indexes
- `ELMOS_SQL_CATALOG_IR_COMPILER-02` — partitioned table
- `ELMOS_SQL_CATALOG_IR_COMPILER-03` — view/materialized view
- `ELMOS_SQL_CATALOG_IR_COMPILER-04` — roles/grants/RLS
- `ELMOS_SQL_CATALOG_IR_COMPILER-05` — identity/sequence/default
- `ELMOS_SQL_CATALOG_IR_COMPILER-06` — vendor extension fallback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
