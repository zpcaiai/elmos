---
name: b31-data-pipeline-migration
description: "Migrate ETL, ELT, streaming, batch, and orchestration workflows using typed pipeline IR while preserving state, watermarks, retries, idempotency, schema evolution, schedules, and data contracts. Use for pipeline implementation."
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

## Skill 1196: Data pipeline, workflow, and orchestration migration

## Use this skill when

- An identified pipeline must move to a new orchestrator, compute engine, warehouse, or lakehouse.
- A database migration requires downstream data flows to follow.
- Legacy scripts or stored procedures should become maintainable pipeline steps.

## Database-specific risks and invariants

- Equivalent transformation code can still duplicate, omit, reorder, or reprocess data.
- Checkpoint, watermark, late-data, retry, and exactly-once-like semantics differ by platform.
- Orchestration defaults, time zones, credentials, and backfill behavior can change.

## Workflow

1. Select a representative pipeline and lock source code, scheduler metadata, schemas, runtime profile, and data fixtures.
2. Emit typed pipeline IR for DAG, steps, transformations, state, watermarks, retries, schedules, resources, secrets, and source/sink contracts.
3. Select an exact target provider profile and generate deterministic jobs, orchestration, configuration, tests, and deployment artifacts.
4. Implement idempotency, checkpoints, backfill, schema evolution, late-data, failure recovery, and observability explicitly.
5. Run source and target on identical fixtures and replay data; compare records, aggregates, ordering, duplicates, checkpoints, errors, and SLAs.
6. Run holdout and representative workloads, fault injection, restart, and cost/performance tests; document cutover and rollback.

## Required repository outputs

- Pipeline IR, target implementation, deployment, and configuration
- Data-contract and lineage updates
- Correctness, restart, performance, cost, and cutover evidence

## Verification

- Run full, incremental, retry, backfill, late-data, schema-change, and partial-failure scenarios.
- Compare output records and business invariants, not just row counts.
- Verify no duplicate side effects and checkpoint recovery.

## Stop and escalate when

- Target cannot preserve required state/checkpoint/idempotency contracts.
- A pipeline must access unapproved production data or credentials.
- Green status depends on dropping late records, retries, or validation steps.

## Definition of done

The certified pipeline runs on the exact target, preserves data and control semantics, has restart/backfill/cutover evidence, meets SLA/cost targets, and is operationally owned.
