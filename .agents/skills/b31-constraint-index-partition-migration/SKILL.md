---
name: b31-constraint-index-partition-migration
description: Migrate primary, unique, foreign, check, exclusion constraints, indexes, clustering, partitioning, storage, and enforcement timing with correctness and performance evidence. Use for structural integrity and physical design migration.
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

## Skill 1187: Constraint, index, clustering, and partition migration

## Use this skill when

- A schema contains nontrivial constraints, filtered/expression indexes, partitions, included columns, or clustered storage.
- Target performance or uniqueness behavior depends on collation, nulls, or enforcement timing.
- An expand-contract migration must phase constraints safely.

## Database-specific risks and invariants

- Unique-null behavior, deferred constraints, FK actions, partial indexes, and partition routing differ by engine.
- Dropping or weakening constraints to load data can leave corrupt production state.
- Physical indexes copied literally can be ineffective or harmful on the target.

## Workflow

1. Extract all logical constraints and physical access structures with dependencies, definitions, validation state, enforcement timing, and workload usage.
2. Represent them in canonical IR, separating integrity requirements from target physical implementation.
3. Generate target constraints and indexes with provider-specific strategies, including staged/not-valid creation where approved.
4. Create partition mapping, data-routing, default-partition, retention, and maintenance plans.
5. Apply to disposable target data, validate constraints, test FK actions and uniqueness/null semantics, and replay representative plans.
6. Measure target query behavior; tune physical design without weakening logical integrity; document exceptions.

## Required repository outputs

- Constraint and physical-design mappings
- Target DDL, phased validation plan, partition and maintenance plan
- Integrity tests, plan evidence, and exceptions

## Verification

- Run positive and negative integrity tests, including nulls, collation, cascades, deferred timing, and partition boundaries.
- Verify indexes are used for representative workloads without unacceptable write amplification.
- Compare catalog enforcement and validate all staged constraints before certification.

## Stop and escalate when

- Certification requires leaving P0 constraints disabled or unvalidated.
- Partition strategy can misroute or orphan data.
- Target cannot enforce required integrity and no approved application-level invariant exists.

## Definition of done

Logical integrity is preserved, physical design is justified by workload evidence, partitions route correctly, all certified constraints validate, and exceptions are explicit.
