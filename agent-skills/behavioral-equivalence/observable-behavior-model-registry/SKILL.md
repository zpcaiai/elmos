---
name: observable-behavior-model-registry
description: "Define and govern Batch 9 Observable Behavior Model profiles and required observation points. Use when registering HTTP, database, message, file, cache, error, audit, timing, resource, or final-state effects for a module."
---

# Observable Behavior Model Registry

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Map each Semantic Obligation and scenario to externally meaningful observations.
2. Register collector, scope, sensitivity, required state and protocol version for every point.
3. Separate observable behavior from internal debug data and record missing coverage.

## Hard rules

- Require at least one point for every critical effect.
- Treat collector failure separately from business difference.
- Block high-level equivalence when a critical observation is absent.

## Output

Emit versioned OBM profiles and observation-point records.

