# GoldenDB Target Adapter

- **Skill ID:** `52-target-goldendb`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **GoldenDB**. Route mode: **exact GoldenDB product/version/deployment mode discovered at runtime**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** GoldenDB is positioned for financial/telecom core workloads; public capability detail varies. This adapter is intentionally strict: it must ingest the exact vendor documentation/capability export available to the deployment before enabling rules.

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

- adapters/target/52-goldendb/capabilities.py
- adapters/target/52-goldendb/types.py
- adapters/target/52-goldendb/ddl.py
- adapters/target/52-goldendb/sql.py
- adapters/target/52-goldendb/procedural.py
- adapters/target/52-goldendb/errors.py
- adapters/target/52-goldendb/plans.py
- adapters/target/52-goldendb/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. No hard-coded assumption that Oracle/MySQL syntax or PL/SQL features are supported unless capability discovery proves it for the deployed version.
4. Prioritize transaction correctness, high availability, failover, sharding/distribution and financial-grade cutover evidence.
5. Use source-to-IR conversion broadly but only render constructs present in target capability catalog.
6. Require vendor/environment capability snapshot as part of E1 and E5 evidence.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Capability discovery absent -> fail closed
- Financial transfer transaction concurrency
- Sequence/key generation under failover
- Large batch + OLTP mix
- Primary/standby or cluster failure drill
- Rollback/recovery rehearsal
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
