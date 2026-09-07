---
name: b31-data-correctness-performance-cutover
description: "Validate schema, data, queries, routines, transactions, pipelines, performance, backfill, CDC, dual-run, cutover, rollback, and production readiness for a database modernization pack. Use before customer acceptance or production transition."
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

## Skill 1201: Data correctness, performance, migration, and cutover validation

## Use this skill when

- A pack is approaching POC acceptance, migration wave, or production cutover.
- Backfill/CDC and source-target coexistence need evidence.
- Schema/query/routine correctness must be combined with operational release gates.

## Database-specific risks and invariants

- Object creation and sample queries can pass while history, deletes, CDC lag, sequence state, transactions, or production workload fail.
- Dual writes can produce partial failures or conflicting authorities.
- Rollback can lose target-period writes if not designed before cutover.

## Workflow

1. Lock source/target artifacts, route profile, workload corpus, data snapshot, acceptance thresholds, privacy, and rollback owners.
2. Provision or clone isolated environments; apply schema and load representative history using checkpointed backfill.
3. Start CDC/delta capture with durable positions and delete handling; establish one authoritative writer and optional shadow reads.
4. Run canonical schema/data/query/routine/transaction/pipeline comparisons, P0 invariants, performance/SLO, security, backup/restore, and failure tests.
5. Execute final delta, generator reset, consumer/caller switch, canary, observation window, and rollback drill.
6. Generate signed evidence, unresolved differences, accepted waivers, customer approvals, and retirement prerequisites.

## Required repository outputs

- Migration/cutover plan and authority state machine
- Backfill/CDC checkpoints and reconciliation results
- Performance, security, DR, rollback, and customer acceptance evidence

## Verification

- Require zero unknown P0 differences, critical precision loss, missing/duplicate records, and unapproved security/transaction regressions.
- Verify CDC caught up, deletes propagated, generators safe, callers migrated, and rollback preserves target-period data.
- Run `run_database_gate.py` on the exact release pack.

## Stop and escalate when

- Initial states, schema versions, or source/target data cannot be proven comparable.
- Critical data, security, transaction, or performance differences remain.
- Rollback or forward-recovery cannot preserve writes made during the target window.

## Definition of done

The exact release is schema/data/query/transaction/performance equivalent for approved scope, migration and rollback are rehearsed, P0 differences are zero, and customer owners have signed the evidence.
