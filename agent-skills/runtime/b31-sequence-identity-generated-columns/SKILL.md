---
name: b31-sequence-identity-generated-columns
description: "Migrate sequences, identity/auto-increment keys, generated and computed columns, defaults, allocation caches, and key-generation contracts without collisions or semantic drift. Use for key and server-generated value migration."
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

## Skill 1188: Sequence, identity, auto-increment, and generated-column migration

## Use this skill when

- Source applications depend on sequences, identity insert, generated columns, computed values, or ORM allocation sizes.
- Data backfill and CDC must preserve keys while new writes continue.
- Target key generation differs from the source.

## Database-specific risks and invariants

- Sequence cache, increment, cycle, allocation size, trigger-generated keys, and identity retrieval differ.
- Backfill can advance target generators incorrectly or create future collisions.
- Computed columns can change determinism, type, indexing, or update behavior.

## Workflow

1. Discover generators, consumers, allocation sizes, start/current values, caches, cycles, ownership, generated expressions, and key retrieval APIs.
2. Model logical key identity separately from physical generator implementation.
3. Choose direct sequence, identity, hi-lo, application allocator, compatibility service, or blocked strategies.
4. Generate backfill-safe procedures to reserve key ranges, preserve explicit keys, reset generators, and coordinate CDC.
5. Implement generated/computed expressions or certified adapters and test insert/update/returning behavior.
6. Run concurrent key-generation, restart, cache-loss, rollback, replication, and cutover tests; document operational controls.

## Required repository outputs

- Generator and computed-column mapping manifest
- Backfill/cutover key-range plan and target DDL
- Collision, concurrency, restart, and retrieval evidence

## Verification

- Insert representative and boundary records on real engines and compare generated values and relationships.
- Test concurrent writers, rollback gaps, sequence restart, explicit identity load, and post-cutover next values.
- Verify ORM/client key retrieval and allocation settings.

## Stop and escalate when

- The target can collide with migrated or concurrently generated keys.
- Generated expressions are nondeterministic or unsupported without an approved replacement.
- Current sequence state or allocation behavior cannot be established.

## Definition of done

Key generation remains collision-free and operationally correct through backfill, CDC, cutover, restart, and application usage, with explicit target ownership and evidence.
