---
name: b31-view-materialized-view-migration
description: "Migrate views, indexed/materialized views, refresh policies, dependencies, security context, updatability, and consumers through query IR and real result comparison. Use for logical and precomputed database views."
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

## Skill 1189: View, indexed view, and materialized-view migration

## Use this skill when

- Source workloads depend on views, materialized/indexed views, synonyms, or reporting layers.
- Refresh, security-definer, or updatable-view semantics matter.
- A target engine requires rewrite, physical table, or pipeline replacement.

## Database-specific risks and invariants

- Flattening views can alter security, nulls, duplicates, ordering, or update behavior.
- Materialized refresh modes and transaction visibility differ.
- Nested dependencies can create cycles or stale downstream objects.

## Workflow

1. Discover view definitions, dependencies, owners, grants, security context, consumers, refresh schedules, indexes, and update paths.
2. Parse definitions into query IR and classify simple, aggregate, recursive, security-sensitive, updatable, and materialized cases.
3. Choose direct view, rewritten view, target materialized view, maintained table, pipeline, façade, or blocked strategy.
4. Generate dependency-ordered DDL and refresh/maintenance jobs with explicit authority and failure handling.
5. Load representative data, compare results and permissions, test updates where applicable, and measure refresh/query performance.
6. Add holdout nested-view cases and record temporary coexistence or consumer migration plans.

## Required repository outputs

- View dependency graph and mapping plan
- Target view/materialization DDL and refresh jobs
- Result, security, freshness, and performance evidence

## Verification

- Compare canonical row sets and data types on source and target.
- Test definer/invoker rights, row security, updatability, refresh consistency, and dependent-object invalidation.
- Run representative report/query workloads.

## Stop and escalate when

- A security-sensitive view loses its access-control semantics.
- Refresh or update behavior cannot meet the business freshness/consistency contract.
- Recursive or provider-specific logic cannot be translated or safely retained.

## Definition of done

Certified views preserve results, security, dependencies, refresh and update contracts, and performance targets with explicit target implementation and lifecycle.
