---
name: b31-etl-elt-discovery
description: "Discover ETL, ELT, batch, streaming, orchestration, schedules, sources, sinks, transformations, checkpoints, retries, secrets, SLAs, and lineage from code, metadata, runtime, and operations. Use before data-pipeline modernization."
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

## Skill 1195: ETL, ELT, batch, streaming, and orchestration discovery

## Use this skill when

- A customer has unknown pipelines, jobs, scripts, schedulers, notebooks, or managed data services.
- Declared DAGs differ from runtime schedules and actual data movement.
- A database migration must include downstream data and analytics workloads.

## Database-specific risks and invariants

- Hidden cron, shell, stored-procedure, file, manual, or partner processes can be missed.
- Runtime watermarks, late data, retry, checkpoints, and secrets may live outside source code.
- Discovery can expose personal data or overload source platforms.

## Workflow

1. Define approved systems, credentials, sampling windows, and data-safety rules.
2. Scan repositories, scheduler APIs, catalogs, notebooks, SQL, job metadata, files, queues, and cloud services.
3. Collect runtime DAGs, schedules, durations, failures, retries, checkpoints, watermarks, data sizes, late-arrival patterns, SLAs, and owners.
4. Build source/sink/transformation/control-flow and column-level lineage candidates with confidence and evidence.
5. Classify active, seasonal, manual, deprecated, shadow, and unknown pipelines.
6. Emit a workload fingerprint, critical-path map, privacy classification, migration candidates, and representative fixtures.

## Required repository outputs

- Pipeline estate inventory and runtime fingerprint
- DAG, dependency, source/sink, SLA, and lineage graph
- Unknowns, critical paths, data classifications, and candidate priorities

## Verification

- Cross-check source repositories, scheduler APIs, runtime logs, storage access, and business-owner interviews.
- Verify seasonal/month-end workloads or document coverage gaps.
- Ensure collection is read-only and sensitive values are minimized/tokenized.

## Stop and escalate when

- Critical source/sink ownership is unknown.
- Discovery requires unsafe production writes or unauthorized payload capture.
- A hidden manual process cannot be represented or owned.

## Definition of done

The data estate has a source-traced, runtime-backed inventory of active pipelines, dependencies, controls, SLAs, data classes, unknowns, and representative migration workloads.
