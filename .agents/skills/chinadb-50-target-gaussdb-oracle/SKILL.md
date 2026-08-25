---
name: chinadb-50-target-gaussdb-oracle
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for GaussDB Oracle-Compatible Target Adapter. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "50-target-gaussdb-oracle"
  source_path: "skills/50-target-gaussdb-oracle/SKILL.md"
  source_sha256: "sha256:0550eae417e2e3e44b10a8cd50000960ae1d29c586c58945465c49c162c7fae5"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# GaussDB Oracle-Compatible Target Adapter

- **Skill ID:** `50-target-gaussdb-oracle`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **GaussDB**. Route mode: **Centralized A-compatible or Distributed Oracle-compatible, exact version**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** Huawei UGO supports Oracle-to-GaussDB assessment/schema conversion and publishes detailed conversion rules. GaussDB has Oracle-compatible modes but documented gaps such as ANYDATA and package-name differences (for example DBMS_* to DBE_* in supported cases).

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

- adapters/target/50-gaussdb-oracle/capabilities.py
- adapters/target/50-gaussdb-oracle/types.py
- adapters/target/50-gaussdb-oracle/ddl.py
- adapters/target/50-gaussdb-oracle/sql.py
- adapters/target/50-gaussdb-oracle/procedural.py
- adapters/target/50-gaussdb-oracle/errors.py
- adapters/target/50-gaussdb-oracle/plans.py
- adapters/target/50-gaussdb-oracle/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Ingest UGO conversion outputs/errors as optional hints/evidence, then run independent semantic validation.
4. Maintain centralized-vs-distributed capability distinctions.
5. Encode advanced-package mappings as versioned semantic rules rather than name-only replacements.
6. Unsupported Oracle object types/packages must produce rewrite/lift/manual strategies.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- DBMS_LOB -> supported DBE mapping
- ANYDATA unsupported/remediation path
- Oracle package/procedure
- Tablespace mapping
- Centralized vs distributed behavior
- Distributed sequence/transaction performance
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

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `50-target-gaussdb-oracle`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
