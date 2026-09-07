# HighGo / HGDB Target Adapter

- **Skill ID:** `47-target-highgo`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **HighGo HGDB**. Route mode: **HGDB version + Oracle compatibility feature set**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** HighGo provides HgMigration tooling and its Oracle-compatibility lineage includes PL/iSQL/IvorySQL-related capabilities; exact enterprise capability must be discovered per version.

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

- adapters/target/47-highgo/capabilities.py
- adapters/target/47-highgo/types.py
- adapters/target/47-highgo/ddl.py
- adapters/target/47-highgo/sql.py
- adapters/target/47-highgo/procedural.py
- adapters/target/47-highgo/errors.py
- adapters/target/47-highgo/plans.py
- adapters/target/47-highgo/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Maintain enterprise HGDB capability catalog separately from community IvorySQL assumptions.
4. Convert Oracle objects/procedural code only against discovered target support.
5. Use PostgreSQL-family behavior as a baseline only where verified; do not assume extension parity.
6. Include telecom/enterprise-scale object-count and rollback tests.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Oracle package/procedure compatibility
- DB2/SQL Server type mappings
- Cross-schema dependencies
- Large object-count migration
- Rollback/resume
- Extension/capability discovery mismatch
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
