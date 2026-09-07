# Semantic Database IR

- **Skill ID:** `02-semantic-db-ir`
- **Version:** `1.0.0`
- **Category:** core/ir
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Define a loss-aware, vendor-neutral intermediate representation for DDL, queries, procedural logic, transactions, security objects and application DB interactions. The IR preserves source semantics and unsupported constructs rather than normalizing them away.

## Inputs

- Parsed source ASTs
- Catalog-resolved symbols/types
- Source session semantics
- Application call-site metadata

## Required outputs

- Versioned IR schema
- Typed symbol/dependency graph
- Semantic operations vocabulary
- Source-map backreferences
- IR serialization/deserialization and canonical hashing

## Implementation modules / repository contract

- ir/model.py
- ir/types.py
- ir/expr.py
- ir/ddl.py
- ir/query.py
- ir/procedural.py
- ir/transaction.py
- ir/security.py
- ir/app_binding.py
- ir/serde.py

## Interfaces and contracts

- Target adapters consume IR, never raw source text as primary conversion input
- Rule DSL predicates operate over typed IR nodes

## Workflow

1. Model scalar/composite/LOB/time/interval/rowid/identity semantics.
2. Represent DDL and physical design separately from logical schema.
3. Represent query semantics including nulls, coercion, collation, ordering, locking and hints.
4. Represent procedural control flow, exceptions, cursors, dynamic SQL and side effects.
5. Represent transaction scope/isolation/autocommit/savepoints.
6. Preserve unknown source nodes with exact text/source span and semantic risk.
7. Version the IR with migrations and golden fixtures.

## Mandatory tests

- Round-trip parse->IR->source-like rendering
- Unknown node preservation
- Precision/scale and timezone fidelity
- Name resolution across synonyms/search paths
- Transaction/control-flow graph correctness
- Backward-compatible IR schema migration

## Required evidence

- IR schema/version manifest
- Golden serialization corpus
- Round-trip diff report
- Hash stability evidence

## Fail-closed / escalation rules

- IR normalization may not erase source behavior needed for differential tests.
- Unknown node cannot be converted as generic SQL.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
