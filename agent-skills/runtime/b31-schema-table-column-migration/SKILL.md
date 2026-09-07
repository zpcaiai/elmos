---
name: b31-schema-table-column-migration
description: "Implement schema, namespace, table, column, default, comment, ownership, and object-name migration through canonical DDL IR with real target provisioning and schema-diff evidence. Use for relational schema transformation."
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

## Skill 1185: Schema, table, column, and namespace migration

## Use this skill when

- A route must create or adapt target catalogs, schemas, tables, or columns.
- Existing DDL generation depends on source text replacement or target conventions.
- A schema upgrade or coexistence plan needs expand-contract DDL.

## Database-specific risks and invariants

- Quoted identifiers, case folding, reserved words, defaults, ownership, comments, temporary objects, and schema search paths differ by engine.
- Recreating schema from ORM metadata can omit production facts.
- Column order or generated defaults can affect applications, unloads, or replication.

## Workflow

1. Capture authoritative source DDL and catalog facts; reconcile them with ORM and migration metadata.
2. Emit canonical schema/table/column nodes with logical identities, physical names, ownership, defaults, comments, storage attributes, and source trace.
3. Select target naming and namespace policies; generate deterministic DDL and an object-by-object mapping manifest.
4. Provision a disposable target, apply DDL in dependency order, and collect target catalog snapshot.
5. Compare canonical source intent with target catalog; add expand-contract steps for coexistence and rollback.
6. Add development, negative, holdout, and representative schema cases; document provider limitations.

## Required repository outputs

- Schema/table/column transformations and target DDL
- Object mapping, naming decisions, schema diff, apply order, rollback/forward-fix plan
- Real target catalog evidence

## Verification

- Apply generated DDL to the exact target engine and compare catalog metadata.
- Test quoted/case-sensitive identifiers, defaults, comments, temporary/unlogged semantics, and schema search path.
- Verify no destructive production operation is emitted without an approved migration step.

## Stop and escalate when

- The authoritative schema is unknown or conflicts cannot be resolved.
- Generation would drop or narrow production data without an approved migration plan.
- A required namespace, ownership, or default semantic cannot be represented safely.

## Definition of done

The declared schema scope provisions on the exact target, matches canonical intent, preserves names/defaults/ownership, has reversible deployment steps, and passes independent schema cases.
