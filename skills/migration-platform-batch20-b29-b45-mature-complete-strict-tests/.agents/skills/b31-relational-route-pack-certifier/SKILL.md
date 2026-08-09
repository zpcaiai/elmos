---
name: b31-relational-route-pack-certifier
description: Implement and certify exact directional Oracle, SQL Server, MySQL, and PostgreSQL route packs, including edition/version features, dialect lowering, routines, drivers, data migration, workload evidence, and maintenance. Use for concrete relational engine routes.
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

## Skill 1200: Oracle, SQL Server, MySQL, and PostgreSQL route-pack implementation

## Use this skill when

- A concrete relational source-to-target route must be created or expanded.
- The route needs engine-specific adapters and provider evidence.
- Candidate routes must be prioritized by customer demand, data risk, tooling, licensing, and representative workload access.

## Database-specific risks and invariants

- Oracle packages/autonomous transactions, SQL Server T-SQL/identity/indexes, MySQL SQL modes/charset, and PostgreSQL extensions/MVCC require distinct strategies.
- Cloud-managed variants can differ from self-managed editions.
- Licensed source engines may not be available in CI, requiring governed customer or partner environments.

## Workflow

1. Score and select one exact directional tuple; confirm licensing, representative workload, owners, and test environment.
2. Scaffold the database pack and implement source discovery plus engine-specific adapter into canonical DB IR.
3. Implement target profile, dialect/type/schema/query/routine/transaction transformations for one P0 vertical workload.
4. Provision real source and target environments; capture exact configurations and driver versions.
5. Run schema, data, query, routine, transaction, plan, performance, backfill/CDC, rollback, holdout, and representative workload suites.
6. Document unsupported features, retained sidecars, compatibility budget, maintenance, economics, and recertification triggers.
7. Invoke the conservative gate; do not infer reverse-route support.

## Required repository outputs

- One exact route pack under `database-packs/<source>-to-<target>`
- Engine-specific adapters, transformations, capability probes, corpora, and evidence
- Customer support profile, restrictions, economics, and maintenance plan

## Verification

- Run exact engine/version/edition probes and real client/driver tests.
- Require P0 schema/data/query/transaction correctness, representative performance, and independent holdout.
- Verify licensing and environment evidence for claims that cannot run in public CI.

## Stop and escalate when

- Exact licensed or representative source environment is unavailable for the claimed scope.
- The route is being generalized from another engine or reverse direction without evidence.
- Critical engine-specific semantics remain unknown or are silently emulated.

## Definition of done

The directional route has real engine evidence, typed adapters, certified transformations, independent workloads, explicit restrictions, maintainers, and only the gate-supported status.
