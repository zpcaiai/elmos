---
name: b31-data-quality-repair
description: Implement data profiling, quality rules, anomaly classification, duplicate and referential checks, migration-defect isolation, controlled repair, reconciliation, and evidence. Use for data-quality readiness and repair loops.
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

## Skill 1197: Data quality profiling, defect classification, and controlled repair

## Use this skill when

- Source data defects block migration or target constraints.
- Reconciliation finds missing, duplicate, invalid, or inconsistent records.
- A route needs objective data-readiness and repair evidence.

## Database-specific risks and invariants

- Silently cleansing source data changes business truth and audit history.
- Migration defects can be misclassified as pre-existing source defects.
- Automatic repair can violate legal hold, financial balances, or referential relationships.

## Workflow

1. Define quality dimensions, critical fields, owners, thresholds, and source-of-truth rules for the data domain.
2. Profile completeness, validity, uniqueness, consistency, referential integrity, precision, timeliness, and distribution using safe snapshots.
3. Classify findings as source defect, migration defect, expected legacy exception, fixture defect, or unknown with record-level evidence.
4. Generate repair candidates with impact, reversibility, approvals, and validation; never mutate authoritative source silently.
5. Apply approved repairs in an isolated or controlled workflow, rerun constraints, queries, reconciliation, and business invariants.
6. Track unresolved issues, waivers, expiry, recurrence, and root-cause improvements to transformations or upstream processes.

## Required repository outputs

- Versioned data-quality rules and profiling results
- Issue inventory, repair plans, approvals, and audit trail
- Post-repair reconciliation and readiness report

## Verification

- Use deterministic rules and stable snapshots; preserve before/after values and digests.
- Verify financial totals, relationships, legal holds, deletes, and tenant boundaries.
- Run negative tests proving invalid auto-repairs are rejected.

## Stop and escalate when

- No business/data owner can approve the repair.
- The proposed repair changes audited or regulated data without an authorized process.
- Unknown discrepancies are being waived or hidden to pass migration.

## Definition of done

Critical data rules are executable, defects are source-traced and correctly classified, repairs are approved/reversible, reconciliation passes, and unresolved risks remain explicit.
