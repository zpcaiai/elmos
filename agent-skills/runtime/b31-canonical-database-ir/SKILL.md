---
name: b31-canonical-database-ir
description: "Implement or extend the typed canonical database IR for catalogs, schemas, types, tables, constraints, indexes, partitions, sequences, views, routines, triggers, queries, transactions, and data pipelines. Use before any cross-dialect transformation."
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

## Skill 1183: Canonical database and data-workload intermediate representation

## Use this skill when

- A new dialect, database object, SQL construct, or pipeline feature must be represented.
- Target generation currently reads source SQL text directly.
- Cross-engine analysis needs stable semantic identities and source maps.

## Database-specific risks and invariants

- A lowest-common-denominator model silently erases engine-specific behavior.
- SQL text normalization can lose quoted identifiers, null ordering, collation, definer rights, or procedural control flow.
- Canonical identities can collide across catalogs, schemas, overloads, editions, or generated objects.

## Workflow

1. Inspect existing IR schemas and adapters; enumerate the exact source constructs and target consumers required by the vertical slice.
2. Add typed nodes for object identity, ownership, names, types, expressions, queries, DDL, routines, triggers, privileges, pipeline steps, and semantic extensions.
3. Preserve source location, original text digest, object dependency edges, provider facts, and unsupported extensions.
4. Represent nullability, precision/scale, collation, time-zone semantics, ordering, constraints, transaction effects, determinism, side effects, and security context explicitly.
5. Implement source adapter emission and target consumer tests; add JSON Schema and reference-integrity validation.
6. Add round-trip or canonicalization tests, negative cases, and stable-ID tests; compare incremental and full rebuild results.

## Required repository outputs

- Versioned `canonical-ir/model.json` artifacts and schema
- Source maps, object identities, dependency graph, unsupported-extension records
- Adapter and consumer conformance tests

## Verification

- Run `validate_canonical_ir.py` on representative IR.
- Parse and emit P0 DDL, queries, routines, and pipeline steps without silent node loss.
- Verify stable IDs, unique object keys, valid references, exact numeric/type metadata, and source trace coverage.

## Stop and escalate when

- A required semantic can only be represented by deleting source behavior or using an untyped string blob with no obligation.
- Consumer changes would make existing certified packs silently reinterpret old IR.
- Canonical IR cannot distinguish security, collation, precision, or transaction behavior needed for correctness.

## Definition of done

The IR expresses the certified scope with typed semantics, provider extensions, stable identities, full source trace, schema validation, reference integrity, and no silent drops.
