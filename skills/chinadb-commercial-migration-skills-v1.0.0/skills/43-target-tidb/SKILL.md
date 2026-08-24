# TiDB Target Adapter

- **Skill ID:** `43-target-tidb`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **TiDB**. Route mode: **TiDB version + SQL mode**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** TiDB DM is primarily for MySQL-compatible full/incremental migration. TiDB documents MySQL compatibility and does not provide stored procedures/functions as a compatibility target.

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

- adapters/target/43-tidb/capabilities.py
- adapters/target/43-tidb/types.py
- adapters/target/43-tidb/ddl.py
- adapters/target/43-tidb/sql.py
- adapters/target/43-tidb/procedural.py
- adapters/target/43-tidb/errors.py
- adapters/target/43-tidb/plans.py
- adapters/target/43-tidb/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. MySQL routes may use native syntax/movement where verified.
4. Oracle/T-SQL stored procedures/functions/triggers must be classified for SQL decomposition or LIFT_TO_APP; never emit fake stored-procedure DDL.
5. Model distributed transaction, auto-increment/auto-random, region/hotspot, unsupported foreign-key/version constraints per target version.
6. Performance certification must include hotspot/skew, distributed plan and batch-write behavior.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- MySQL DM-compatible full+CDC route
- Oracle package lifted to Java/.NET service
- Trigger lifted to event/app logic
- T-SQL procedure with temp table lifted/restructured
- Auto increment concurrency
- Hot-key distributed workload
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
