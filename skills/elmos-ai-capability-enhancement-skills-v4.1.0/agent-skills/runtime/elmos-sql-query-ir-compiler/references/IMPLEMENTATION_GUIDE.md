# Implementation Guide — SQL Query IR Compiler

## Purpose

Compile DML and query semantics including joins, CTEs, windows, aggregates, merge/upsert, returning, JSON, temporal, geospatial and ordering into typed Query IR.

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

1. Use parser plus catalog-aware validation
2. Infer types, nullability and coercions
3. Represent relational algebra and effects
4. Preserve ordering and cardinality assumptions
5. Capture dynamic SQL boundaries

## Native acceptance corpus

- `ELMOS_SQL_QUERY_IR_COMPILER-01` — join/aggregate/window
- `ELMOS_SQL_QUERY_IR_COMPILER-02` — recursive CTE
- `ELMOS_SQL_QUERY_IR_COMPILER-03` — merge/upsert/returning
- `ELMOS_SQL_QUERY_IR_COMPILER-04` — JSON and temporal query
- `ELMOS_SQL_QUERY_IR_COMPILER-05` — pagination/order stability
- `ELMOS_SQL_QUERY_IR_COMPILER-06` — dynamic SQL boundary

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
