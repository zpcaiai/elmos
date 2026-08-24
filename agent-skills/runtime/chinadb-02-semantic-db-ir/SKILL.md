---
name: chinadb-02-semantic-db-ir
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Semantic Database IR. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "02-semantic-db-ir"
  source_path: "skills/02-semantic-db-ir/SKILL.md"
  source_sha256: "sha256:48ac1d5090a4bc7b70abcdf848820b4897183dde3b93abb8dbc52101eeb8ba19"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Semantic Database IR

- **Skill ID:** `02-semantic-db-ir`
- **Version:** `1.0.0`
- **Category:** core/ir
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Define a loss-aware, vendor-neutral intermediate representation for DDL, queries, procedural logic, transactions, security objects and application DB interactions. The IR preserves source semantics and unsupported constructs rather than normalizing them away.

## Inputs

- Parsed source ASTs
- Catalog-resolved symbols/types
- Source session semantics
- Application call-site metadata

## Required outputs

- Versioned IR schema
- Typed symbol/dependency graph
- Semantic operations vocabulary
- Source-map backreferences
- IR serialization/deserialization and canonical hashing

## Implementation modules / repository contract

- ir/model.py
- ir/types.py
- ir/expr.py
- ir/ddl.py
- ir/query.py
- ir/procedural.py
- ir/transaction.py
- ir/security.py
- ir/app_binding.py
- ir/serde.py

## Interfaces and contracts

- Target adapters consume IR, never raw source text as primary conversion input
- Rule DSL predicates operate over typed IR nodes

## Workflow

1. Model scalar/composite/LOB/time/interval/rowid/identity semantics.
2. Represent DDL and physical design separately from logical schema.
3. Represent query semantics including nulls, coercion, collation, ordering, locking and hints.
4. Represent procedural control flow, exceptions, cursors, dynamic SQL and side effects.
5. Represent transaction scope/isolation/autocommit/savepoints.
6. Preserve unknown source nodes with exact text/source span and semantic risk.
7. Version the IR with migrations and golden fixtures.

## Mandatory tests

- Round-trip parse->IR->source-like rendering
- Unknown node preservation
- Precision/scale and timezone fidelity
- Name resolution across synonyms/search paths
- Transaction/control-flow graph correctness
- Backward-compatible IR schema migration

## Required evidence

- IR schema/version manifest
- Golden serialization corpus
- Round-trip diff report
- Hash stability evidence

## Fail-closed / escalation rules

- IR normalization may not erase source behavior needed for differential tests.
- Unknown node cannot be converted as generic SQL.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `02-semantic-db-ir`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
