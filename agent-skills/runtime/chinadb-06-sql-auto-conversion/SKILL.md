---
name: chinadb-06-sql-auto-conversion
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL Automatic Conversion. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "06-sql-auto-conversion"
  source_path: "skills/06-sql-auto-conversion/SKILL.md"
  source_sha256: "sha256:4de4353433986072c90102199c5366158f74a7720f0dad4e5a69726d16d10fae"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# SQL Automatic Conversion

- **Skill ID:** `06-sql-auto-conversion`
- **Version:** `1.0.0`
- **Category:** core/conversion
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Automatically rewrite SELECT/DML/CTE/window/hierarchical/pagination/locking/merge/upsert/dynamic SQL into target dialect while preserving result, error and concurrency semantics.

## Inputs

- Resolved SQL IR
- Bind metadata and expected result types
- Source session semantics
- Target adapter rule pack
- Critical query workload

## Required outputs

- Target SQL
- Bind remapping
- Risk/unsupported annotations
- Query-level differential evidence
- Optional tuning variants

## Implementation modules / repository contract

- convert/sql/rewriter.py
- convert/sql/functions.py
- convert/sql/pagination.py
- convert/sql/hierarchy.py
- convert/sql/dml.py
- convert/sql/locking.py
- convert/sql/hints.py
- convert/sql/binds.py

## Interfaces and contracts

- SQL is parsed to IR; target renderers never operate as blind regex translators

## Workflow

1. Resolve source names/types before rewriting.
2. Rewrite functions/operators/coercions/null semantics through semantic operations.
3. Convert pagination, hierarchical queries, merge/upsert, sequences and returning/output clauses.
4. Convert locking and isolation-sensitive SQL with explicit risk.
5. Strip/translate hints only through target planner semantics.
6. Generate differential fixtures for every high-risk rewrite.
7. Optionally generate target-optimized SQL only after baseline equivalence passes.

## Mandatory tests

- NULL/empty-string comparisons
- Implicit numeric/string conversion
- Date arithmetic
- DST/timezone formatting
- Collation/case/accent sensitivity
- TOP/ROWNUM/LIMIT ties
- ORDER BY stability
- MERGE concurrency
- SELECT FOR UPDATE
- Identity/sequence retrieval
- Error codes for duplicate/FK/overflow

## Required evidence

- Per-query rule trace
- Source vs target results
- Error/SQLSTATE mapping
- Plan capture for critical queries

## Fail-closed / escalation rules

- Unstable result ordering must be represented as unordered comparison, not forced arbitrary ORDER BY.
- Concurrency-sensitive rewrites require transactional tests.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `06-sql-auto-conversion`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
