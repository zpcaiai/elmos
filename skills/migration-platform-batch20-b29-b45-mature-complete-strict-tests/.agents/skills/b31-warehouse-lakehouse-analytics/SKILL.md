---
name: b31-warehouse-lakehouse-analytics
description: Migrate warehouses, lakehouses, dimensional models, SCD logic, aggregates, semantic metrics, BI models, row security, file/table formats, and incremental analytics workloads. Use for analytical platform modernization.
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

## Skill 1199: Warehouse, lakehouse, semantic model, and analytics migration

## Use this skill when

- Facts, dimensions, marts, reports, notebooks, semantic metrics, or lakehouse tables must move.
- A target analytics platform changes storage, compute, SQL, or security models.
- Business reports must remain numerically and semantically consistent.

## Database-specific risks and invariants

- Metric definitions, slowly changing dimensions, surrogate keys, late facts, fiscal calendars, and row security are easy to change silently.
- File formats, table formats, partitioning, compaction, and incremental models affect correctness and cost.
- Report parity can be hidden by aggregate-only checks.

## Workflow

1. Inventory warehouse/lakehouse objects, facts/dimensions, SCD types, aggregates, metrics, semantic models, reports, notebooks, consumers, security, and workload/cost.
2. Map logical business metrics and dimensional contracts into canonical IR independent of the current tool.
3. Select exact target storage/table/compute/BI profiles; generate schema, transformations, incremental models, security, and orchestration.
4. Migrate representative history with stable surrogate/business key strategy, late-arrival handling, and fiscal/time logic.
5. Compare row-level facts, dimensions, aggregates, metrics, report outputs, row security, freshness, performance, and cost.
6. Run holdout periods and reports; document retained tools, coexistence, cutover, and rollback.

## Required repository outputs

- Analytics workload and metric inventory
- Target warehouse/lakehouse models, transformations, security, and orchestration
- Row/metric/report correctness, freshness, performance, and cost evidence

## Verification

- Reconcile detail rows before aggregates.
- Test SCD, late facts, fiscal periods, null/unknown members, row security, and incremental rebuilds.
- Compare P0 report and metric results on independent periods.

## Stop and escalate when

- Business metric definitions or owners are unknown.
- Migration passes aggregates but fails underlying facts/dimensions.
- Row security, retention, or regulated data controls cannot be preserved.

## Definition of done

Certified analytical workloads preserve business metrics, dimensional history, security, freshness, performance, and cost targets with independent report and row-level evidence.
