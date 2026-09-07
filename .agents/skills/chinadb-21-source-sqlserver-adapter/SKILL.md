---
name: chinadb-21-source-sqlserver-adapter
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for SQL Server / T-SQL Source Adapter. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "21-source-sqlserver-adapter"
  source_path: "skills/21-source-sqlserver-adapter/SKILL.md"
  source_sha256: "sha256:272ba51b18bfd10c9ad5115f93218263b5f93cfeba09e5361c81459f81912de1"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# SQL Server / T-SQL Source Adapter

- **Skill ID:** `21-source-sqlserver-adapter`
- **Version:** `1.0.0`
- **Category:** source-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `01-estate-inventory-assessment`, `02-semantic-db-ir`

## Objective

Extract SQL Server catalog and T-SQL semantics including identity, temp/table variables, TRY/CATCH, OUTPUT, MERGE, linked servers, jobs and transaction/error behavior.

## Inputs

- SQL Server connection/catalog privileges
- Engine/version/session settings
- Optional workload traces and app repositories

## Required outputs

- Normalized source AST + Semantic IR
- Catalog/dependency snapshot
- Session semantics fingerprint
- Unsupported external dependency list

## Implementation modules / repository contract

- adapters/source/sqlserver/catalog.py
- adapters/source/sqlserver/parser.py
- adapters/source/sqlserver/semantics.py
- adapters/source/sqlserver/workload.py

## Interfaces and contracts

- Implements source adapter protocol: `discover`, `extract_catalog`, `parse`, `semantics`, `capture_workload`

## Workflow

1. Discover exact engine/version/config before extraction.
2. Extract all object classes and dependencies with source definitions.
3. Parse SQL/procedural code and resolve symbols/types.
4. Capture source session/transaction/error semantics.
5. Export a deterministic source fingerprint and coverage counts.

## Mandatory tests

- Identity/sequence/computed columns, filtered indexes, schemas
- Stored procedures/functions/triggers, temp tables/table variables
- TOP/OFFSET, OUTPUT, APPLY, MERGE, hints
- TRY/CATCH, XACT_STATE, @@ROWCOUNT, SCOPE_IDENTITY
- Linked servers, SQL Agent job references, CLR/external dependencies
- Collation and case/accent sensitivity, datetime/money/uniqueidentifier
- Insufficient catalog privilege detection
- Quoted/mixed-case names
- Cross-schema dependencies

## Required evidence

- Catalog object counts vs extracted counts
- Parser coverage
- Source fingerprint
- Known-unknown dependency report

## Fail-closed / escalation rules

- If an object cannot be parsed, preserve raw source and mark unsupported; do not drop it.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `21-source-sqlserver-adapter`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
