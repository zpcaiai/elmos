---
name: b31-database-modernization-factory
description: Implement and certify a directional, version-specific database or data-platform modernization pack with workload discovery, canonical database IR, schema/query/routine/pipeline transformations, real source/target execution, data reconciliation, holdout workloads, and evidence. Use for Batch 31 pack creation or major expansion.
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

## Skill 1181: Database and data-platform modernization factory orchestrator

## Use this skill when

- A user asks to add a database-engine migration, upgrade, stored-procedure modernization, or data-platform route.
- An existing database pack lacks runtime workload evidence, typed canonical IR, representative data, or independent certification.
- Multiple Batch 31 skills must be coordinated into one production-shaped vertical slice.

## Database-specific risks and invariants

- Database behavior depends on engine version, edition, compatibility mode, collation, session settings, extensions, statistics, and runtime workload—not DDL text alone.
- A schema that creates successfully can still lose precision, change null/order semantics, break locking, or regress production queries.
- Data migration and database-object translation require separate correctness, performance, security, rollback, and business-owner evidence.

## Workflow

1. Inspect existing adapters, database packs, canonical IR, migration jobs, evidence schemas, and repository-native verification commands; write `database-packs/<pack>/certification/gap-inventory.md`.
2. Confirm accountable, maintenance, and data owners; exact source/target engine, version, edition, charset, collation, time zone, extensions, and the first representative workload.
3. Scaffold the pack when absent, then implement static and runtime workload fingerprinting before generating target objects.
4. Emit typed canonical IR for one complete vertical slice covering schema, constraints, one query workload, one transactional behavior, and any routine or pipeline on the critical path.
5. Select or implement an exact target profile and deterministic transformations; provision disposable source and target databases.
6. Execute real source and target DDL, data loading, queries, routines, transactions, and reconciliation; collect plans and performance where required.
7. Run development, negative, holdout, and representative-workload suites; fix systemic failures in discovery, IR, capability, or transformation layers.
8. Write data-safety, lifecycle, economics, rollback, and certification evidence, then invoke the gate rather than manually raising status.

## Required repository outputs

- `database-packs/<pack-key>/pack.json`, `support-matrix.json`, and `route-matrix.json`
- `source-fingerprint/`, `canonical-ir/`, `target-profile/`, and `transformations/`
- `migration/`, `reconciliation/`, `corpus/{development,holdout,representative-workloads}/`
- `certification/{evidence.json,certification.json,gate-result.json}`

## Verification

- Provision exact source and target engines or approved licensed environments and run health/version probes.
- Apply source and target DDL, seed representative data, run P0 queries/routines/transactions, and compare canonical results.
- Run `validate_database_pack.py`, `validate_canonical_ir.py`, and `run_database_gate.py`.
- Verify one representative workload passes schema, data, query, transaction, performance, rollback, and evidence requirements.

## Stop and escalate when

- No owner, exact engine tuple, disposable environment, or data-safety approval exists.
- The only implementation strategy is regex-based SQL replacement or lossy coercion without explicit obligations.
- Green status requires weakening constraints, row security, transaction semantics, data checks, or holdout tests.
- Independent holdout or representative-workload evidence is unavailable for a certification claim.

## Definition of done

The pack contains executable workload discovery, typed canonical IR, an exact target profile, deterministic transformations, real engine execution, data reconciliation, independent corpora, explicit limitations, rollback evidence, and only the strongest gate-supported status.
