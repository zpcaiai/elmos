---
name: b31-database-certification-gate
description: "Run the conservative Batch 31 certification gate for a database or data-platform pack and emit certified, limited, experimental, or blocked status from exact tuples, workload fingerprints, canonical IR, real execution, reconciliation, holdout, performance, security, and cutover evidence."
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

## Skill 1202: Batch 31 database modernization certification gate

## Use this skill when

- A pack requests certification or release-status change.
- Engine, driver, extension, schema, query, routine, pipeline, or migration behavior changed.
- A customer needs a machine-readable support statement.

## Database-specific risks and invariants

- Status fields can be manually edited without evidence.
- Passing development fixtures does not prove representative workloads or production data safety.
- Aggregate success rates can hide one critical precision, security, transaction, or data failure.

## Workflow

1. Run the deterministic pack validator, canonical IR validator, schema validators, and evidence-reference checks.
2. Verify exact source/target tuples, owners, runtime fingerprints, canonical IR coverage, target profile, route matrix, and data-safety plan.
3. Execute or validate stored evidence for real source/target provisioning, P0 schema/type/query/routine/transaction/pipeline tests, data reconciliation, performance, security, rollback, and restore.
4. Verify development, negative, holdout, and representative workload separation and non-empty evidence.
5. Check all critical counters, unknowns, silent drops, precision/collation/data/security/transaction regressions, test integrity, and destructive changes.
6. Emit gate result and strongest justified status; downgrade or block on any missing critical evidence.

## Required repository outputs

- `certification/gate-result.json` and human-readable gate report
- Machine-readable certification status, restrictions, exact tuple, metrics, and evidence refs
- Recertification triggers and unresolved blockers

## Verification

- Run `python3 scripts/batch31/run_database_gate.py database-packs/<pack>`.
- Independently verify evidence paths, digests, exact engine probes, holdout, and representative workloads.
- Attempt negative certification with missing evidence and ensure the gate fails.

## Stop and escalate when

- Any critical evidence is missing, stale, unverifiable, or from the wrong engine tuple.
- P0 unknowns, silent drops, precision loss, data differences, transaction/security regressions, or test-integrity violations are nonzero.
- The pack lacks independent holdout or representative workload evidence.

## Definition of done

The gate emits a reproducible, conservative status tied to exact engines, versions, editions, drivers, configurations, scope, metrics, evidence, restrictions, and maintenance ownership; status cannot be raised by editing metadata alone.
