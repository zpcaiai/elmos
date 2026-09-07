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
