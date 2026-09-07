# GBase 8c Target Adapter

- **Skill ID:** `45-target-gbase8c`
- **Version:** `1.0.0`
- **Category:** target-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `02-semantic-db-ir`, `03-rule-mutation-dsl`, `05-ddl-auto-conversion`, `06-sql-auto-conversion`, `07-plsql-tsql-conversion`

## Objective

Implement the production target adapter for **GBase 8c**. Route mode: **exact distributed deployment/version**. The adapter owns target rendering, type/function/procedural capability mapping, catalog apply/introspection, error mapping, plan capture and operational hooks.

**Native leverage:** GBase publishes Oracle RAC-to-GBase 8c migration practices; use vendor tools when available but treat distributed semantics as a separate certification concern.

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

- adapters/target/45-gbase8c/capabilities.py
- adapters/target/45-gbase8c/types.py
- adapters/target/45-gbase8c/ddl.py
- adapters/target/45-gbase8c/sql.py
- adapters/target/45-gbase8c/procedural.py
- adapters/target/45-gbase8c/errors.py
- adapters/target/45-gbase8c/plans.py
- adapters/target/45-gbase8c/operations.py

## Interfaces and contracts

- Implements target adapter: `discover`, `render`, `apply`, `introspect`, `map_error`, `capture_plan`, `movement_hooks`, `operational_checks`
- Every capability is keyed by exact target version/mode

## Workflow

1. Discover target version, compatibility mode, enabled extensions/features and topology.
2. Load only compatible versioned rules.
3. Convert schema/query logic through Semantic IR with distribution-aware physical design separated from logical equivalence.
4. Map sequences/identity, partitioning and cross-node transaction assumptions explicitly.
5. Generate distribution key/index recommendations after baseline E3 passes.
6. E4 must measure data skew, distributed joins and write contention.
7. Apply generated objects to an ephemeral target; introspect actual catalog and compile status.
8. Run target-specific differential and performance fixtures before route certification.

## Mandatory tests

- Oracle RAC-style sequence concurrency
- Partitioned tables
- Cross-shard transaction
- Distributed join
- Skew/hot-key workload
- Failover/retry transaction semantics
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
