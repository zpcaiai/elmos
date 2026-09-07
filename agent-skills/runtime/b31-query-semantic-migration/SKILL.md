---
name: b31-query-semantic-migration
description: "Parse and migrate SQL, JPQL/HQL, ORM-generated, dynamic, and native queries through typed query IR while preserving null, join, aggregation, ordering, pagination, date, JSON, recursive, locking, and parameter semantics. Use for query translation."
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

## Skill 1191: Query semantic migration and cross-dialect execution

## Use this skill when

- A route must translate application, report, ORM, or routine queries.
- Queries compile on the target but return different rows, ordering, precision, or errors.
- Native or dynamic SQL needs certified conversion.

## Database-specific risks and invariants

- Null comparison, implicit casts, empty strings, collation, join behavior, grouping, set operations, window frames, pagination, date math, and JSON operators differ.
- Result ordering is undefined unless explicitly required.
- Dynamic SQL can hide injection, object-name, and parameter-binding behavior.

## Workflow

1. Collect query text/templates, parameter types, callers, result contracts, execution frequency, plans, and representative parameter sets.
2. Parse into typed query IR with scopes, bindings, expressions, joins, aggregates, windows, ordering, limits, locks, hints, and source trace.
3. Resolve source semantics and target capabilities; choose direct lowering, rewrite, retained SQL, view/procedure adapter, or blocked strategy.
4. Generate parameterized target query and explicit casts/collations/order where required; preserve result shape and error contracts.
5. Execute source and target over identical fixtures and parameter distributions; compare canonical row multisets/sequences and exceptions.
6. Add negative and holdout queries, then feed accepted queries into plan/performance validation.

## Required repository outputs

- Query inventory, typed IR, target SQL/query objects, and source maps
- Parameter/result contracts and semantic obligations
- Differential result and error evidence

## Verification

- Run real source and target query execution for boundary and representative parameters.
- Compare row values, types, cardinality, duplicates, explicit ordering, nulls, and exceptions.
- Scan generated SQL for unsafe interpolation and validate prepared parameter binding.

## Stop and escalate when

- Complex queries are being transformed by regex or string substitution.
- A P0 query has unknown result ordering, precision, security, or lock semantics.
- Correctness depends on unapproved client-side evaluation or broad result tolerances.

## Definition of done

Certified queries are typed, parameterized, executable, result- and error-equivalent for declared inputs, source-traced, independently tested, and performance-ready.
