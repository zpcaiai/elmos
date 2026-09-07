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
