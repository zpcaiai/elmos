---
name: b31-orm-database-contract
description: Coordinate ORM mappings, existing database schema, migration ownership, query generation, converters, transactions, change tracking, and schema evolution across application and database modernization. Use where ORM and database routes intersect.
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

## Skill 1194: ORM, database contract, and schema-authority coordination

## Use this skill when

- JPA/Hibernate, EF Core, SQLAlchemy, Django ORM, or another ORM owns part of the data contract.
- Generated ORM schema conflicts with production DDL or database-route transformations.
- Application and database migrations must be sequenced together.

## Database-specific risks and invariants

- Two tools can both believe they own schema migration.
- ORM conventions can change names, types, precision, relationships, cascade, loading, query semantics, or concurrency.
- Client-side conversion can hide provider incompatibility and performance regressions.

## Workflow

1. Inventory ORM models, migrations, conventions, type converters, generated queries, session/context lifetime, transactions, and actual database schema.
2. Define authoritative ownership for schema, migrations, data transformations, and runtime query generation.
3. Map ORM logical types/relationships to canonical DB IR and exact target profile; generate explicit configuration where conventions are unsafe.
4. Coordinate expand-contract schema, application releases, migration ordering, and rollback.
5. Run model validation, generated SQL capture, query/result tests, transaction/concurrency tests, and schema-diff checks on real target.
6. Document retained provider-specific behavior, client-side evaluation blockers, and maintenance ownership.

## Required repository outputs

- ORM-to-database contract and ownership matrix
- Explicit target mappings, migration ordering, and generated-SQL evidence
- Schema/query/transaction compatibility report

## Verification

- Compare ORM metadata to target catalog and canonical IR.
- Execute CRUD, relationships, converters, queries, transactions, and concurrency paths.
- Ensure only one approved mechanism performs each schema change.

## Stop and escalate when

- ORM and database tooling both perform uncontrolled schema writes.
- Correctness requires unapproved client-side evaluation or weakened database constraints.
- Actual production schema cannot be reconciled with application metadata.

## Definition of done

ORM and database ownership is unambiguous, target mappings and generated SQL are validated, schema releases are coordinated, and P0 data/transaction behavior is equivalent.
