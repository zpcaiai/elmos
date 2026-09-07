---
name: environment-version-and-state-alignment
description: "Align source and target configuration, versions, identity, locale, timezone and initial state for comparable Batch 9 runs. Use before executing any differential scenario."
---

# Environment Version and State Alignment

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Compare business configuration and every feature flag.
2. Align database seed, cache, broker, files, permissions, tenant/principal and external recordings.
3. Record runtime differences and decide whether each affects comparability.

## Hard rules

- Do not accept visually similar configuration as proof.
- Version every seed and preserve independent generated-ID streams.
- Mark an unalignable critical scenario not-comparable.

## Output

Emit one alignment manifest per run or scenario with explicit differences and evidence.

