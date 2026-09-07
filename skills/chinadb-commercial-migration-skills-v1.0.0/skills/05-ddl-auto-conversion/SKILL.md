# DDL Automatic Conversion

- **Skill ID:** `05-ddl-auto-conversion`
- **Version:** `1.0.0`
- **Category:** core/conversion
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Convert logical and physical schema objects using AST/IR rules, preserving dependencies and explicitly separating semantically required objects from target-specific physical tuning.

## Inputs

- DDL IR and dependency graph
- Target adapter capabilities
- Naming/tablespace/storage policy
- Security mapping policy

## Required outputs

- Ordered target DDL
- Converted-object manifest
- Unsupported/manual review list
- Physical-design recommendations
- Compile/apply evidence

## Implementation modules / repository contract

- convert/ddl/planner.py
- convert/ddl/mapper.py
- convert/ddl/render.py
- convert/ddl/dependencies.py
- convert/ddl/physical.py

## Interfaces and contracts

- Emits `conversion-result.schema.json` per object
- Target adapter owns render/mapping details

## Workflow

1. Topologically order users/schemas/types/tables/sequences/views/procedural objects/indexes/constraints/grants.
2. Map data types by semantic range/precision, not spelling.
3. Convert identity/sequence/default generation with concurrency semantics.
4. Convert partitioning/materialized views/temp tables/synonyms where target supports them.
5. Separate required logical DDL from optional target tuning.
6. Apply target DDL to an ephemeral target and introspect the resulting catalog.

## Mandatory tests

- Numeric boundary types
- Empty string vs NULL
- Timestamp/TZ/DST
- Case-folded identifiers
- Deferrable constraints
- Function-based indexes
- Partial/filtered indexes
- Partition/subpartition boundaries
- Materialized view refresh semantics
- Synonyms/search path

## Required evidence

- DDL conversion trace
- Target compilation/apply log
- Catalog diff
- Unsupported object report

## Fail-closed / escalation rules

- If a constraint cannot be preserved, do not silently drop it.
- Physical tuning must not alter logical semantics without evidence.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
