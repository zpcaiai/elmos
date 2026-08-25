# GBase 8a Target Adapter

- **Skill ID:** `46-target-gbase8a`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **GBase 8a**. Route mode: **8a analytical/MPP product profile**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** GBase documents `orato8a` for Oracle extraction/migration and enterprise MPP migration scenarios.

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

- adapters/target/46-gbase8a/capabilities.py
- adapters/target/46-gbase8a/types.py
- adapters/target/46-gbase8a/ddl.py
- adapters/target/46-gbase8a/sql.py
- adapters/target/46-gbase8a/procedural.py
- adapters/target/46-gbase8a/errors.py
- adapters/target/46-gbase8a/plans.py
- adapters/target/46-gbase8a/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Treat 8a primarily as an analytical/MPP target; do not promise OLTP procedural equivalence without a route-specific capability proof.
4. Rewrite OLAP SQL and physical design with distribution/replication/partition strategy.
5. Separate result equivalence from target-optimized query shape.
6. Performance gate is workload-level and includes skew, shuffle, concurrency and load throughput.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Large fact/dimension join
- Oracle analytic/window SQL
- CTAS/bulk load
- Distribution-key skew
- High-concurrency BI
- Oracle-to-8a extraction reconciliation
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
