---
name: sql-dialect-routine-validation
description: Validate SQL dialect, DDL/DML, stored routine, trigger, transaction, and analytics-platform conversion by dual-database execution.
---

# SQL Dialect and Routine Validation

## Inputs

Source dialect/version, target dialect/version, schemas, routines, data profiles, workloads, transaction/concurrency scenarios, accepted adaptations and performance budgets.

## Workflow

### 1. Parse and inventory

Build lossless AST and symbol/dependency graph for tables, types, sequences, views, routines, packages, triggers, dynamic SQL, privileges, jobs and platform objects. Preserve comments/metadata when required.

### 2. Provision dual databases

Use pinned container/image digests or approved managed test instances. Apply equivalent normalized dataset with boundary values, NULL, Unicode, Decimal, timezone/DST, collation and constraint violations.

### 3. Execute source baseline

Collect result sets, OUT parameters, errors, row counts, DB state, sequence values, trigger effects, transaction trace, locks and performance.

### 4. Convert

Emit target SQL and an adaptation manifest. Unsupported package state, autonomous transactions, hints or platform services must be explicit with target design and proof obligations.

### 5. Execute target

Run identical logical workload. Normalize only documented nondeterministic fields. Compare ordered/unordered results correctly and inspect all affected state.

### 6. Routine scenarios

For procedures/functions/triggers/packages test normal, boundary, exception, nested call, cursor empty/multiple, dynamic SQL, savepoint, rollback, security definer/invoker, concurrent sessions and partial failure.

### 7. Fuzz/metamorphic

Generate SQL from grammar/AST and DB states; apply semantics-preserving rewrites; differential against source/target and, where suitable, reference DBMS. Reduce failing statements and data to minimal repro.

### 8. Performance

Correctness is mandatory before plan/performance. Compare latency/throughput/scan bytes and flag pathological regressions, but do not demand identical physical plans across engines.

## Required comparisons

- result values/types/order;
- error category and abort scope;
- inserted/updated/deleted rows;
- triggers, sequences, generated keys;
- commit/rollback/savepoint;
- schema constraints and privileges;
- analytics partition/distribution/cost semantics.

## Critical rule

A target statement that executes successfully with different results is a silent semantic error, not a partial success.
