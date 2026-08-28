# Implementation Guide — SQL Routine and Trigger IR Compiler

## Purpose

Compile stored procedures, functions, packages, triggers, cursors, handlers, exceptions, dynamic SQL, session state and transaction control into Routine IR.

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

1. Use vendor-native parsers or runtime metadata
2. Model variables, cursors, exceptions and control flow
3. Capture transaction/session side effects
4. Link dynamic SQL and called routines
5. Preserve trigger ordering and firing semantics

## Native acceptance corpus

- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-01` — PL/SQL package
- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-02` — T-SQL procedure
- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-03` — PL/pgSQL function
- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-04` — trigger cascade
- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-05` — cursor/handler/exception
- `ELMOS_SQL_ROUTINE_TRIGGER_IR_COMPILER-06` — autonomous/session transaction

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
