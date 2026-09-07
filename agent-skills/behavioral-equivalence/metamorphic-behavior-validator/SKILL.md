---
name: metamorphic-behavior-validator
description: "Validate reviewed Batch 9 metamorphic relations when a complete expected output is unavailable. Use for idempotency, ordering, aggregation, scaling, pagination, caching, retry and roundtrip properties."
---

# Metamorphic Behavior Validator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Derive the relation from a domain rule or proof.
2. Run base and transformed inputs against both systems with isolated effects.
3. Compare the declared output, state and message relation and preserve both inputs.

## Hard rules

- Do not invent business invariants with an Agent.
- Do not replace critical Golden scenarios with metamorphic tests.
- Treat both systems failing the relation as a source-bug candidate.

## Output

Emit relation definitions, paired observations and differential verdicts.

