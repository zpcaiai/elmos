---
name: chinadb-48-target-oceanbase-oracle
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for OceanBase Oracle-Compatible Target Adapter. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "48-target-oceanbase-oracle"
  source_path: "skills/48-target-oceanbase-oracle/SKILL.md"
  source_sha256: "sha256:2daaac3828ba049599c393419466fe6e3dab9ec297360918bd6e736b59a7fdd0"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# OceanBase Oracle-Compatible Target Adapter

- **Skill ID:** `48-target-oceanbase-oracle`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **OceanBase**. Route mode: **Oracle-compatible tenant**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** OMS supports Oracle schema/full/incremental migration; OceanBase Oracle mode supports a majority of Oracle syntax/procedural features, while documented incompatibilities still exist. OMA can provide assessment signals.

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

- adapters/target/48-oceanbase-oracle/capabilities.py
- adapters/target/48-oceanbase-oracle/types.py
- adapters/target/48-oceanbase-oracle/ddl.py
- adapters/target/48-oceanbase-oracle/sql.py
- adapters/target/48-oceanbase-oracle/procedural.py
- adapters/target/48-oceanbase-oracle/errors.py
- adapters/target/48-oceanbase-oracle/plans.py
- adapters/target/48-oceanbase-oracle/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Use OMS/OMA as optional movement/assessment providers but independently verify converted schema/application behavior.
4. Maintain unsupported Oracle type/package/feature matrix by OceanBase version.
5. Test ROWID/partition-key/timezone/LOB edge cases called out by vendor migration documentation.
6. E4 includes distributed transaction, locality, hot partition and failover behavior.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Oracle package/procedure/function
- ROWID-sensitive partition update
- TIMESTAMP WITH TIME ZONE historical DST case
- LOB boundary/performance
- Sequence concurrency
- Distributed failover/retry
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

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `48-target-oceanbase-oracle`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
