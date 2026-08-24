---
name: chinadb-05-ddl-auto-conversion
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for DDL Automatic Conversion. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "05-ddl-auto-conversion"
  source_path: "skills/05-ddl-auto-conversion/SKILL.md"
  source_sha256: "sha256:5043945ca97a0a07ff207fd0646b6d6dd554fc5cd38f5ecfbe0b7dcc728cd857"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# DDL Automatic Conversion

- **Skill ID:** `05-ddl-auto-conversion`
- **Version:** `1.0.0`
- **Category:** core/conversion
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Convert logical and physical schema objects using AST/IR rules, preserving dependencies and explicitly separating semantically required objects from target-specific physical tuning.

## Inputs

- DDL IR and dependency graph
- Target adapter capabilities
- Naming/tablespace/storage policy
- Security mapping policy

## Required outputs

- Ordered target DDL
- Converted-object manifest
- Unsupported/manual review list
- Physical-design recommendations
- Compile/apply evidence

## Implementation modules / repository contract

- convert/ddl/planner.py
- convert/ddl/mapper.py
- convert/ddl/render.py
- convert/ddl/dependencies.py
- convert/ddl/physical.py

## Interfaces and contracts

- Emits `conversion-result.schema.json` per object
- Target adapter owns render/mapping details

## Workflow

1. Topologically order users/schemas/types/tables/sequences/views/procedural objects/indexes/constraints/grants.
2. Map data types by semantic range/precision, not spelling.
3. Convert identity/sequence/default generation with concurrency semantics.
4. Convert partitioning/materialized views/temp tables/synonyms where target supports them.
5. Separate required logical DDL from optional target tuning.
6. Apply target DDL to an ephemeral target and introspect the resulting catalog.

## Mandatory tests

- Numeric boundary types
- Empty string vs NULL
- Timestamp/TZ/DST
- Case-folded identifiers
- Deferrable constraints
- Function-based indexes
- Partial/filtered indexes
- Partition/subpartition boundaries
- Materialized view refresh semantics
- Synonyms/search path

## Required evidence

- DDL conversion trace
- Target compilation/apply log
- Catalog diff
- Unsupported object report

## Fail-closed / escalation rules

- If a constraint cannot be preserved, do not silently drop it.
- Physical tuning must not alter logical semantics without evidence.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `05-ddl-auto-conversion`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
