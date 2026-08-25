---
name: chinadb-49-target-oceanbase-mysql
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for OceanBase MySQL-Compatible Target Adapter. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "49-target-oceanbase-mysql"
  source_path: "skills/49-target-oceanbase-mysql/SKILL.md"
  source_sha256: "sha256:44c2d2e89b782b60bf9aec17435da4bb698a0bfb00b8140d4ee10d611362cfa8"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# OceanBase MySQL-Compatible Target Adapter

- **Skill ID:** `49-target-oceanbase-mysql`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **OceanBase**. Route mode: **MySQL-compatible tenant**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** OMS plus OceanBase MySQL mode provide a native migration/compatibility path for MySQL-like workloads.

## Inputs

- Semantic DB IR
- Source adapter fingerprint
- Target connection + exact version/mode
- Rule packs and capability catalog
- Route SLO/security policy

## Required outputs

- Target DDL/SQL/procedural artifacts
- Target capability snapshot
- Apply/compile diagnostics
- Error and plan adapters
- Movement/CDC integration hooks
- Target-specific E3/E4/E5 fixtures

## Implementation modules / repository contract

- adapters/target/49-oceanbase-mysql/capabilities.py
- adapters/target/49-oceanbase-mysql/types.py
- adapters/target/49-oceanbase-mysql/ddl.py
- adapters/target/49-oceanbase-mysql/sql.py
- adapters/target/49-oceanbase-mysql/procedural.py
- adapters/target/49-oceanbase-mysql/errors.py
- adapters/target/49-oceanbase-mysql/plans.py
- adapters/target/49-oceanbase-mysql/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Honor MySQL sql_mode/charset/collation differences explicitly.
4. Convert PostgreSQL/other SQL only through Semantic IR and target feature proof.
5. Map auto increment, generated keys and transaction retry semantics.
6. Run distributed hotspot/partition/performance verification.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- MySQL auto_increment and on-duplicate
- sql_mode strictness
- charset/collation
- generated columns
- batch writes/hot key
- failover transaction retry
- Target version upgrade boundary
- Unsupported construct fail-closed
- Error-code/domain exception mapping
- Explain-plan capture

## Required evidence

- Capability snapshot + hash
- Conversion/apply traces
- Target catalog diff
- Target-specific E3/E4 results
- Operational capability evidence

## Fail-closed / escalation rules

- Unknown target version/mode blocks conversion.
- Missing capability rule emits UNSUPPORTED/MANUAL_REVIEW, never optimistic compatibility.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `49-target-oceanbase-mysql`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
