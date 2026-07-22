---
name: batch-9-conformance-and-gate-controller
description: "Evaluate Batch 9 coverage, equivalence, stability, evidence and module gates E-A through E-E. Use for the final behavioral-equivalence admission decision."
---

# Batch 9 Conformance and Gate Controller

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Compute scenario, endpoint, database, transaction, observation, property, metamorphic, flaky and trace metrics per module.
2. Apply E-A comparability, E-B public contract, E-C state/effect, E-D production-hardening admission and optional E-E confidence thresholds.
3. List every blocker, approved change, restriction and open obligation.

## Hard rules

- Do not let repository averages hide a failed module.
- Keep unknown, approved and flaky results outside strict equivalence.
- Never set cutover eligibility true in Batch 9.

## Output

Emit per-module conformance and only admit E-D/E-E modules to Batch 10.

