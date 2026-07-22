---
name: procedure-function-trigger-package-and-job-modernizer
description: Modernize PL/SQL, T-SQL, MySQL routines, PL/pgSQL, packages, triggers, CLR routines, and database jobs by choosing conversion, application extraction, external scheduling, temporary retention, or redesign. Use for stored business logic and scheduler migrations where transaction and side-effect equivalence matter.
---

# Procedure and Job Modernization

## Classify before changing

- Inventory procedures, functions, package specs/bodies, triggers, events, scheduler jobs, cursors, dynamic SQL, user types, and CLR routines.
- Classify complexity as LOW, MEDIUM, HIGH, or CRITICAL from transactions, state, dynamic SQL, temporary objects, external calls, and business criticality.
- Choose target procedure, application service, batch job, stream processor, temporary source retention, managed feature, or manual redesign per object.

## Preserve hidden behavior

- Model Oracle package state, initialization, overloads, exceptions, cursors, bulk operations, autonomous transactions, and row/type references.
- Classify triggers by audit, derived data, validation, sync, side effect, security, or unknown; trace recursive order, messages, sequences, and hidden writes.
- Preserve scheduler timezone, credential boundary, retry, concurrency, and idempotency.
- Compare begin/commit/rollback/savepoint, isolation, locks, deadlocks, exception behavior, and retry.

## Gate high risk

- Let agents propose candidates, but require humans to approve financial logic, package-state design, trigger removal, transaction refactoring, and scheduler cutover.
- Emit inventories, strategies, converted sources, extraction plans, trigger/job plans, and differential validation.
- Block automatic conversion for critical routines or unresolved runtime-dependent SQL.
