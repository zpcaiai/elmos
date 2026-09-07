---
name: b31-routine-trigger-migration
description: "Migrate database functions, procedures, packages, triggers, dynamic SQL, cursors, exceptions, transactions, security context, and side effects to target routines, application services, or retained sidecars. Use for procedural database logic."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-30 contracts, database adapters, framework packs, runner jobs, evidence models, build commands, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at design notes when executable discovery, typed IR, transformations, database fixtures, validation, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch31/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch31/QUALITY_GATES.md`
- `../../../docs/batch31/REPOSITORY_LAYOUT.md`
- `../../../docs/batch31/VERSION_POLICY.md`
- `../../../docs/batch31/DATA_SAFETY_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch31/scaffold_database_pack.py ...`
- `python3 scripts/batch31/validate_database_pack.py ...`
- `python3 scripts/batch31/validate_canonical_ir.py ...`
- `python3 scripts/batch31/run_database_gate.py ...`

## Global constraints

- Treat each database or data-platform route as directional, engine/version/edition/provider-specific, and independently certified. Reverse migration is a separate pack.
- Capture exact engine versions, editions, compatibility modes, drivers, extensions, character sets, collations, time zones, SQL modes, and runtime configuration. Never claim generic support for an engine family from one tuple.
- Use real source and target database engines or an approved licensed environment. Parser-only output is not evidence that DDL, SQL, routines, transactions, or data behave correctly.
- Parse DDL, SQL, routines, and pipelines into typed canonical representations. Do not implement complex transformations with regular-expression replacement.
- Preserve precision, scale, signedness, null semantics, collation, case sensitivity, time-zone behavior, ordering, constraint timing, transaction isolation, locking, security, row-level policies, grants, and error contracts.
- Never write to production or customer-authoritative databases unless a separately approved production workflow explicitly authorizes it. Use snapshots, clones, disposable schemas, or synthetic fixtures for development and certification.
- Keep development, negative, holdout, and representative-workload corpora physically separate. Do not author transformations from holdout cases.
- Prefer deterministic mappings and certified compatibility adapters. Model-generated SQL or code is a candidate and must pass the same parser, execution, reconciliation, performance, security, and test-integrity gates.
- Record unsupported, conditional, lossy, and unknown behavior explicitly. Never hide it by dropping objects, coercing money to floating point, weakening constraints, disabling triggers or row security, or broadening tolerances after failures.
- Fix repeated failures in discovery, canonical IR, provider capability models, transformations, or generators instead of patching many target objects independently.
- Record source snapshots, target snapshots, transformation versions, model/prompt versions, runner/toolchain digests, query-plan evidence, reconciliation results, and approvals.
- Run the narrowest relevant tests first, then independent holdout and representative workloads, and finally the conservative Batch 31 gate before making release claims.

## Skill 1190: Stored routine, package, and trigger migration

## Use this skill when

- Source business logic resides in PL/SQL, T-SQL, stored procedures, functions, packages, or triggers.
- A route must decide which logic remains in the database versus moves to an application service.
- Dynamic SQL or trigger side effects block schema migration.

## Database-specific risks and invariants

- Procedural languages differ in types, exception handling, cursor semantics, transaction control, autonomous transactions, package state, and security definer behavior.
- Moving trigger or routine logic can change ordering, atomicity, performance, and hidden consumers.
- Regex translation can create code that compiles but is semantically wrong.

## Workflow

1. Inventory routines, overloads, package state, callers, grants, dynamic SQL, cursors, temp tables, transaction control, triggers, recursion, and side effects.
2. Parse procedural code into typed routine/control-flow IR with source maps, effects, transaction, security, and determinism metadata.
3. Classify each object as direct target routine, rewritten routine, application service, generated adapter, retained sidecar, or blocked.
4. Implement the smallest P0 routine/trigger slice deterministically; generate application contracts for moved logic.
5. Execute source and target with representative data and error paths; compare result sets, OUT values, data changes, messages, audit, and rollback.
6. Measure performance and concurrency, add holdout routines, and document deployment/cutover ordering.

## Required repository outputs

- Routine/trigger inventory and strategy decisions
- Typed IR, target routine/application implementation, adapters, and call-site changes
- Execution, side-effect, error, performance, and rollback evidence

## Verification

- Compile and execute routines on real source and target engines.
- Compare all outputs and side effects, including triggers and failure rollback.
- Test dynamic SQL parameterization, definer rights, package/session state, and concurrent execution.

## Stop and escalate when

- The only approach is regex translation or broad exception swallowing.
- Autonomous transaction, security-definer, trigger ordering, or package state cannot be preserved safely.
- Hidden callers or side effects remain unknown for a P0 routine.

## Definition of done

Every certified procedural object has an explicit placement strategy, executable implementation, caller migration, side-effect and rollback equivalence, performance evidence, and no silent trigger or security loss.
