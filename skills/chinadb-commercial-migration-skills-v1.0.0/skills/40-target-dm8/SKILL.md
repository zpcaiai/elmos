# DM8 Target Adapter

- **Skill ID:** `40-target-dm8`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **DM8**. Route mode: **DM8 compatible-mode profile selected per route**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** DTS / SQLark may be orchestrated for assessment, object/data movement and comparison where available. DM8 documents broad SQL compatibility and heterogeneous migration support.

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

- adapters/target/40-dm8/capabilities.py
- adapters/target/40-dm8/types.py
- adapters/target/40-dm8/ddl.py
- adapters/target/40-dm8/sql.py
- adapters/target/40-dm8/procedural.py
- adapters/target/40-dm8/errors.py
- adapters/target/40-dm8/plans.py
- adapters/target/40-dm8/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Oracle PL/SQL: prefer native DM-compatible conversion when semantics are proven; otherwise rewrite/lift.
4. T-SQL: map identity, functions, TOP/pagination, temp objects, error handling and procedures through IR.
5. Type mapping must test VARCHAR2 length/page-size constraints, NUMBER precision, LOBs, DATE/TIMESTAMP and empty-string/null behavior.
6. Generate DM-specific catalog introspection, explain-plan capture and error mapping.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Oracle package/procedure/trigger
- Oracle varchar2/LOB boundary
- Sequence/identity concurrency
- SQL Server identity + OUTPUT equivalent
- Hierarchical/pagination SQL
- DM compatible-mode switch matrix
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
