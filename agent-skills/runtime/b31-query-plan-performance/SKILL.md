---
name: b31-query-plan-performance
description: "Compare source and target query plans, cardinality, statistics, indexes, latency, throughput, resource usage, and plan stability for representative workloads. Use after query correctness and before production certification."
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

## Skill 1192: Query-plan, workload, and performance comparison

## Use this skill when

- Correct target queries regress latency, IO, CPU, memory, locks, or throughput.
- Target physical design or statistics need evidence-backed tuning.
- A customer requires performance SLO and capacity proof.

## Database-specific risks and invariants

- The same logical query can use radically different but valid plans; textual plan equality is not a goal.
- Cold cache, stale statistics, parameter sniffing, adaptive plans, or environment mismatch can invalidate results.
- Adding hints or indexes for one case can harm other workloads and writes.

## Workflow

1. Define representative workload, parameter distributions, concurrency, warm-up, data scale, cache state, and source/target SLOs.
2. Capture normalized source and target plans, estimates, actual rows, timings, IO, CPU, waits, spills, locks, and statistics versions.
3. Classify regressions by cardinality, join strategy, access path, sort/hash spill, parallelism, parameter sensitivity, partition pruning, or network behavior.
4. Tune target query, statistics, indexes, partitions, configuration, or generated SQL using deterministic changes with workload-wide impact analysis.
5. Repeat controlled runs and compare percentile latency, throughput, resources, plan stability, and write amplification.
6. Record accepted differences, capacity assumptions, rollback, and ongoing plan-regression monitors.

## Required repository outputs

- Normalized plan and workload evidence
- Performance regression analysis and tuning changes
- SLO/capacity report and production monitor definitions

## Verification

- Run multiple controlled iterations with exact environment and dataset digests.
- Require query correctness before accepting performance evidence.
- Test hot/cold, representative parameter distributions, concurrency, and statistics refresh behavior.

## Stop and escalate when

- Environment or dataset differences make comparison invalid.
- A proposed hint/index weakens correctness or creates unreviewed workload regressions.
- P0 SLOs fail and no approved capacity or architecture plan exists.

## Definition of done

Representative target workloads meet approved correctness and SLOs with reproducible plans, justified physical design, capacity evidence, and regression monitoring.
