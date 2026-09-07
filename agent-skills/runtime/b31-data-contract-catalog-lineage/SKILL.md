---
name: b31-data-contract-catalog-lineage
description: "Migrate and govern data contracts, catalog metadata, ownership, classifications, SLOs, schema versions, column-level lineage, transformations, and consumer compatibility. Use for catalog and lineage modernization."
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

## Skill 1198: Data contract, catalog, ownership, and lineage migration

## Use this skill when

- A migration needs machine-readable producer/consumer contracts and ownership.
- Catalog or lineage metadata must move with databases and pipelines.
- Consumers need compatibility and deprecation controls.

## Database-specific risks and invariants

- Technical schema alone does not describe business meaning, freshness, quality, privacy, or ownership.
- Lineage inferred only from SQL misses dynamic, procedural, file, or manual steps.
- Renaming or merging fields can break consumers even when data loads succeed.

## Workflow

1. Inventory contracts, schemas, owners, classifications, glossary, quality rules, SLAs/SLOs, retention, consumers, and catalog systems.
2. Create versioned canonical data contracts with logical fields, physical mappings, semantics, compatibility mode, and deprecation policy.
3. Build table/column/object/pipeline/report lineage from typed IR plus runtime evidence and confidence.
4. Generate target catalog entries, contract tests, ownership mappings, classifications, and consumer notifications.
5. Validate producer and consumer compatibility across coexistence windows; track unknown lineage and manual evidence.
6. Integrate contract/lineage changes with schema, pipeline, BI, privacy, and cutover gates.

## Required repository outputs

- Versioned data contracts and compatibility policy
- Catalog/glossary/ownership/classification migration
- Column-level lineage graph with confidence and evidence

## Verification

- Run contract tests against source and target data/products.
- Trace P0 fields end-to-end through transformations to reports or APIs.
- Verify ownership, classification, retention, and consumer inventories are complete.

## Stop and escalate when

- P0 data has no accountable owner or semantic definition.
- Lineage gaps prevent safe deletion, privacy handling, or consumer cutover.
- A breaking contract change has no version/coexistence plan.

## Definition of done

P0 data products have approved contracts, owners, classifications, compatibility tests, source-traced lineage, consumer migration plans, and no unknown critical paths.
