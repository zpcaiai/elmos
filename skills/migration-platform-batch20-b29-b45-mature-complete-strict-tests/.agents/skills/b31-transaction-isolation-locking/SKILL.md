---
name: b31-transaction-isolation-locking
description: Migrate and verify autocommit, transaction boundaries, isolation, savepoints, locking, MVCC, deadlocks, retries, DDL transactions, and concurrency error contracts across database engines. Use for transactional correctness.
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

## Skill 1193: Transaction, isolation, locking, and concurrency migration

## Use this skill when

- Source and target engines differ in isolation, locking, MVCC, savepoint, or DDL transaction behavior.
- An application or routine depends on lock hints, deadlock retry, autonomous transactions, or transaction-local state.
- Production cutover requires proof against lost updates and partial commits.

## Database-specific risks and invariants

- Isolation names do not guarantee identical anomalies.
- Autocommit, implicit transactions, lock escalation, gap locks, predicate locks, snapshot semantics, and DDL behavior differ.
- Automatic retries can duplicate non-idempotent side effects.

## Workflow

1. Discover transaction boundaries from code, routines, drivers, pools, session settings, queries, and runtime lock/deadlock evidence.
2. Define logical transaction contracts: atomicity, visible anomalies, read/write sets, isolation needs, timeouts, locks, retries, and error mappings.
3. Map to exact target engine/driver behavior; implement explicit isolation, savepoints, locks, or application coordination where required.
4. Create controlled concurrent schedules for dirty/nonrepeatable/phantom reads, write skew, lost updates, deadlocks, lock timeouts, and rollback.
5. Execute on real source and target; compare allowed outcomes, final state, errors, retry side effects, and performance.
6. Document conditional provider behavior, operational monitoring, and production rollback.

## Required repository outputs

- Transaction and concurrency contract inventory
- Target transaction/locking configuration and code/routine changes
- Controlled-schedule, rollback, deadlock, and anomaly evidence

## Verification

- Run deterministic concurrent tests and repeated randomized schedules.
- Verify no partial commit, lost update, cross-tenant leakage, or duplicate side effects.
- Check driver defaults, pool reset behavior, transaction-local settings, and error mapping.

## Stop and escalate when

- The target cannot meet a P0 atomicity/isolation contract and no approved redesign exists.
- Retry is proposed without idempotency or side-effect controls.
- Concurrency tests are nondeterministic and cannot be replayed.

## Definition of done

P0 transaction contracts have explicit target implementation, controlled-schedule evidence, correct rollback/error behavior, no forbidden anomalies, and operational controls.
