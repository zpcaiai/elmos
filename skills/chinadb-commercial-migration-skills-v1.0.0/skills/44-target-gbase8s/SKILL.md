# GBase 8s Target Adapter

- **Skill ID:** `44-target-gbase8s`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **GBase 8s**. Route mode: **exact 8s version/cluster mode**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** GBase 8s documents Oracle-compatible object coverage plus MTK full migration and RTSync incremental/reverse synchronization capabilities.

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

- adapters/target/44-gbase8s/capabilities.py
- adapters/target/44-gbase8s/types.py
- adapters/target/44-gbase8s/ddl.py
- adapters/target/44-gbase8s/sql.py
- adapters/target/44-gbase8s/procedural.py
- adapters/target/44-gbase8s/errors.py
- adapters/target/44-gbase8s/plans.py
- adapters/target/44-gbase8s/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Leverage native Oracle-compatible objects when version capabilities prove equivalence.
4. Integrate MTK/RTSync through adapter hooks when available but preserve independent checksum/E3 evidence.
5. Map SQL Server/DB2 constructs through shared IR.
6. Capture HA/cluster failover behavior in production certification for critical routes.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Oracle materialized view/sequence/synonym/package
- MTK resume/recovery
- RTSync incremental/reverse positions
- DB2 identity/sequence
- SQL Server procedure subset
- HA failover during workload
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
