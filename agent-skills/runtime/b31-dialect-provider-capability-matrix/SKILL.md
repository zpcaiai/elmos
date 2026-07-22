---
name: b31-dialect-provider-capability-matrix
description: "Create and maintain exact database dialect, engine version, edition, extension, driver, and provider capability matrices with evidence-backed support states. Use for route claims, target selection, upgrades, and conditional feature decisions."
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

## Skill 1184: Dialect, engine, edition, and provider capability matrix

## Use this skill when

- A route needs exact supported tuples and conditional capabilities.
- Target selection depends on sequences, JSON, spatial, partitioning, isolation, collations, extensions, or operational constraints.
- A database version, edition, compatibility mode, or driver changes.

## Database-specific risks and invariants

- The same product name can expose different behavior by version, edition, compatibility level, extension, cloud provider, or session setting.
- Documentation support does not prove the feature works with the selected driver and deployment profile.
- Fallback emulation can introduce correctness or performance regressions.

## Workflow

1. Inventory exact source and target tuples, including engine, version, edition, compatibility mode, cloud service tier, driver, extensions, charset, collation, and time-zone data.
2. Define capability IDs across schema, types, SQL, routines, transactions, security, replication, CDC, backup, performance, and operations.
3. Assign certified, supported, conditional, experimental, detected-only, or blocked status with owner, reason, evidence, and fallback strategy.
4. Implement executable probes for capabilities used by the route; store probe results and environment digests.
5. Update route and target-profile selection logic; add negative tests that prevent unsupported tuples from matching.
6. Run impact analysis and recertification when versions, drivers, extensions, or service tiers change.

## Required repository outputs

- `support-matrix.json`, `route-matrix.json`, and executable capability probes
- Exact tuple evidence and conditional/blocked explanations
- Target-selection and recertification inputs

## Verification

- Provision each claimed tuple and execute its capability probes.
- Verify floating versions and mutable service tiers are rejected.
- Ensure every certified capability has evidence and every conditional/blocked capability has reason and owner.

## Stop and escalate when

- The environment tuple is unknown or uses floating `latest` semantics.
- A claimed feature cannot be executed in the actual edition/provider profile.
- The fallback would weaken correctness, security, durability, or data guarantees.

## Definition of done

The route has a machine-readable, exact, executable capability matrix that drives planning and prevents unsupported engine tuples or provider assumptions from being certified.
