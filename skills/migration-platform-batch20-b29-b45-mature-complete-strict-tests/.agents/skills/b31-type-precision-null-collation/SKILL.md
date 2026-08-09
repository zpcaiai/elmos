---
name: b31-type-precision-null-collation
description: Implement and certify cross-engine data type, precision, scale, null, charset, collation, time-zone, JSON/XML/spatial, enum, and binary mappings with boundary data tests. Use whenever data representation can change.
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

## Skill 1186: Data type, precision, null, charset, collation, and time mapping

## Use this skill when

- A database route maps columns, parameters, variables, or result-set types.
- Money, large integers, strings, timestamps, JSON, spatial, or binary data may be lossy.
- Collation or time-zone behavior changes between source and target.

## Database-specific risks and invariants

- Money converted to floating point, truncated strings, changed Unicode normalization, or reduced timestamp precision cause silent corruption.
- Null, empty string, NaN, infinity, unsigned ranges, and time-zone semantics differ.
- Collation changes equality, uniqueness, indexes, ordering, and query results.

## Workflow

1. Inventory source type declarations and runtime min/max/length/precision distributions for the certified scope.
2. Define canonical logical types plus exact physical metadata: precision, scale, length units, signedness, nullability, charset, collation, time zone, and provider extensions.
3. Select direct, widened, encoded, compatibility, domain-type, or blocked target strategies; generate explicit obligations for lossy or conditional mappings.
4. Build boundary fixtures covering min/max, scale, rounding, null/empty, Unicode, collation, DST, binary zeros, JSON numbers, and special values.
5. Load source and target fixtures, round-trip values, compare canonical results, and test index/constraint behavior under target collation.
6. Emit a type-mapping report, compatibility budget, and customer-visible restrictions.

## Required repository outputs

- Type mapping registry and generated type adapters
- Boundary data corpus and round-trip evidence
- Precision/collation/time-zone obligations and report

## Verification

- Require exact money and P0 numeric equality.
- Run Unicode, collation, null, date/time, JSON, binary, enum, and overflow boundary suites on real engines.
- Verify target DDL and drivers expose the intended types and parameter bindings.

## Stop and escalate when

- A mapping loses P0 precision, scale, range, identity, or time-zone semantics.
- The only proposed strategy converts money to float or ignores collation.
- Required runtime data distribution cannot be sampled safely enough to justify narrowing.

## Definition of done

Every certified type mapping is executable, boundary-tested, source-traced, non-lossy for declared scope, and all conditional/lossy cases are explicit obligations or blockers.
