---
name: database-final-state-differential-comparator
description: "Compare Batch 9 source-target logical database state across physical schema differences. Use for entity, aggregate, projection or event-sourced state validation."
---

# Database Final State Differential Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Apply reviewed table/entity/key/column transformations.
2. Compare existence, count, value, null, Decimal, relation, order, version, delete, tenant, audit and constraints.
3. Link every difference to the triggering scenario and write trace.

## Hard rules

- Treat row count, soft-versus-hard delete, Decimal and tenant drift as meaningful.
- Do not let matching aggregates hide wrong details.
- Preserve trigger and relation effects.

## Output

Emit logical and physical database diffs with ID mappings and evidence.

