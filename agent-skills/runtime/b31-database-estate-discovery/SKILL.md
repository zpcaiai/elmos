---
name: b31-database-estate-discovery
description: "Discover and fingerprint database estates, schemas, runtime workloads, security, storage, dependencies, and operational behavior from catalogs, DDL, statistics, query logs, plans, jobs, and configuration. Use before database modernization planning or certification."
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

## Skill 1182: Database estate, workload, and runtime discovery

## Use this skill when

- A migration pack needs a trustworthy source inventory.
- Catalog exports, DDL, ORM metadata, and runtime usage disagree.
- A customer asks for database modernization assessment or route sizing.

## Database-specific risks and invariants

- Declared objects can be unused while dynamic SQL, synonyms, database links, jobs, grants, or extensions carry critical behavior.
- Sampling windows can miss month-end, batch, or rare failure workloads.
- Discovery queries can overload production or expose sensitive SQL and values.

## Workflow

1. Inspect existing discovery jobs and source-egress policy; define read-only credentials, sampling window, and customer-approved collection scope.
2. Collect engine/edition/version, compatibility mode, charset, collation, time zone, extensions, parameters, roles, grants, schemas, objects, sizes, statistics, jobs, links, and dependencies.
3. Collect runtime evidence: top SQL by latency/CPU/IO, query plans, waits, locks, deadlocks, transaction rates, batch schedules, and failed statements.
4. Classify each fact as declared, active, conditional, generated, test-only, deprecated, or unknown with source trace and confidence.
5. Emit a versioned workload fingerprint and coverage report; identify unsupported objects, missing periods, privacy-sensitive data, and environment assumptions.
6. Add deterministic fixtures and tests for discovered P0 patterns; feed the fingerprint into route prioritization and canonical IR extraction.

## Required repository outputs

- `source-fingerprint/manifest.json` and `evidence.json`
- Catalog, configuration, security, dependency, workload, plan, and storage snapshots
- Coverage, unknowns, collection limits, and data-safety report

## Verification

- Run discovery against a disposable representative database and, when approved, a read-only production replica.
- Cross-check catalog counts, DDL exports, ORM metadata, runtime SQL, and dependency graphs.
- Verify collection queries are read-only, bounded, parameterized, and do not capture literal secrets or PII unnecessarily.

## Stop and escalate when

- Only a stale spreadsheet or ORM model is available and runtime behavior is required.
- Required collection would write to production, take unsafe locks, or exceed approved load.
- Critical business periods or encrypted/protected schemas cannot be observed.

## Definition of done

The pack has a reproducible, source-traced workload fingerprint with exact engine facts, object and dependency coverage, runtime workload evidence, explicit unknowns, and safe collection provenance.
