# Sybase ASE Source Adapter

- **Skill ID:** `25-source-sybase-adapter`
- **Version:** `1.0.0`
- **Category:** source-adapter
- **Implementation status:** specification only until repository evidence proves otherwise
- **Depends on:** `01-estate-inventory-assessment`, `02-semantic-db-ir`

## Objective

Extract ASE schema and T-SQL-like procedural behavior for routes that must modernize older enterprise workloads.

## Inputs

- Sybase ASE connection/catalog privileges
- Engine/version/session settings
- Optional workload traces and app repositories

## Required outputs

- Normalized source AST + Semantic IR
- Catalog/dependency snapshot
- Session semantics fingerprint
- Unsupported external dependency list

## Implementation modules / repository contract

- adapters/source/sybase/catalog.py
- adapters/source/sybase/parser.py
- adapters/source/sybase/semantics.py
- adapters/source/sybase/workload.py

## Interfaces and contracts

- Implements source adapter protocol: `discover`, `extract_catalog`, `parse`, `semantics`, `capture_workload`

## Workflow

1. Discover exact engine/version/config before extraction.
2. Extract all object classes and dependencies with source definitions.
3. Parse SQL/procedural code and resolve symbols/types.
4. Capture source session/transaction/error semantics.
5. Export a deterministic source fingerprint and coverage counts.

## Mandatory tests

- identity/default/rule objects
- stored procedures/triggers
- temporary tables and transaction semantics
- isql/bcp operational dependencies
- datatype and datetime/money semantics
- legacy join/SQL constructs
- Insufficient catalog privilege detection
- Quoted/mixed-case names
- Cross-schema dependencies

## Required evidence

- Catalog object counts vs extracted counts
- Parser coverage
- Source fingerprint
- Known-unknown dependency report

## Fail-closed / escalation rules

- If an object cannot be parsed, preserve raw source and mark unsupported; do not drop it.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
