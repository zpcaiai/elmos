---
name: multi-oracle-equivalence-decision-engine
description: "Combine exact, canonical, schema, contract, state, effect, property, metamorphic, invariant and manual Oracles for Batch 9. Use to adjudicate one observation pair or scenario."
---

# Multi Oracle Equivalence Decision Engine

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Load the scenario's required and optional Oracle set.
2. Run each Oracle independently and preserve conflicts and evidence.
3. Derive final status without averaging away a required failure.

## Hard rules

- A failed required Oracle cannot be cancelled by another pass.
- Keep unknown and not-run nonpassing.
- Require stricter Oracles for security, money and transactions.

## Output

Emit an explainable decision record with every Oracle result and blocker.

